"""Node C: Article selection and summarization."""

from __future__ import annotations

from app.agent.llm_tasks import DeterministicAgentLLM
from app.agent.nodes.base import WorkflowError, agent_node, articles_by_id, llm_reason
from app.agent.nodes.research import retrieve_articles
from app.agent.services import AgentServices
from app.agent.state import AgentState
from app.models.domain import ExecutionPlan
from app.services.telemetry import NodeContext

MAX_SELECTED = 7


def compute_limitations(
    selected_count: int, requested: int, snippet_count: int, undated: int, user_selected: bool = False,
    available: int | None = None,
) -> list[str]:
    notes = []
    if user_selected and selected_count != requested and (available is None or available >= requested):
        notes.append(f"The reviewer selected {selected_count} article(s) (the plan targeted {requested}).")
    elif selected_count < requested:
        notes.append(
            f"Only {selected_count} suitable article(s) were found for the requested {requested}; "
            "no stories were invented to fill the gap."
        )
    if snippet_count:
        notes.append(
            f"{snippet_count} of {selected_count} summaries are based on search snippets because the full "
            "article could not be retrieved."
        )
    if undated:
        notes.append(f"{undated} article(s) have no verifiable publication date and are labelled accordingly.")
    return notes


@agent_node("selection")
def summarize_node(state: AgentState, ctx: NodeContext, svc: AgentServices) -> dict:
    plan = ExecutionPlan.model_validate(state["plan"])
    cfg = plan.config
    by_id = articles_by_id(state)
    chosen_ids = state.get("selected_ids") or state.get("proposed_ids") or []
    chosen_ids = [i for i in dict.fromkeys(chosen_ids) if i in by_id][:MAX_SELECTED]
    if not chosen_ids:
        raise WorkflowError("No articles were selected for the newsletter.")
    approved_by = "user" if state.get("selected_ids") else "agent"

    selected = [by_id[i] for i in chosen_ids]
    pending = [a for a in selected if a.retrieval_status == "not_attempted"]
    if pending:
        updated = {a.id: a for a in retrieve_articles(pending, ctx, svc)}
        selected = [updated.get(a.id, a) for a in selected]
        for a in updated.values():
            by_id[a.id] = a
    for a in selected:
        ctx.log(f"Selected: {a.title[:100]} ({a.publisher}; score {a.final_score:.2f})", "info")
    ctx.log(f"{len(selected)} article(s) selected by the {approved_by}.", "success")
    ctx.stage_event("completed")

    # --- Summarization ---------------------------------------------------
    ctx.stage = "summarization"
    ctx.stage_event("running")
    ctx.check_cancelled()
    warnings = list(state.get("warnings", []))
    basis = sum(1 for a in selected if a.content_basis == "full_text")
    with ctx.track(f"llm.summarize ({svc.llm.name})", f"{len(selected)} articles ({basis} full text)") as h:
        try:
            summaries = svc.llm.summarize(selected, cfg)
            h.success(f"{len(summaries)} summaries")
        except Exception as exc:
            h.fallback("LLM summarization failed; using extractive summaries from source text.", str(exc))
            summaries = []
            warnings.append(
                f"{llm_reason(exc)}, so summaries are sentences copied from each article instead of AI-written."
            )
            ctx.log(f"Summarizer unavailable ({type(exc).__name__}); using extractive fallback.", "warning")
    got = {s.article_id for s in summaries}
    missing = [a for a in selected if a.id not in got]
    if missing:
        summaries += DeterministicAgentLLM().summarize(missing, cfg)
        if got:
            ctx.log(f"{len(missing)} article(s) had no LLM summary; extractive fallback used.", "warning")
    order = {a.id: i for i, a in enumerate(selected)}
    summaries.sort(key=lambda s: order[s.article_id])

    snippet_count = sum(1 for a in selected if a.content_basis != "full_text")
    undated = sum(1 for a in selected if not a.published_date)
    limitations = compute_limitations(
        len(selected), cfg.article_count, snippet_count, undated,
        user_selected=approved_by == "user", available=len(by_id),
    )
    ctx.log(f"Summarized {len(summaries)} article(s).", "success")
    return {
        "selected_ids": [a.id for a in selected],
        "candidates": [by_id[a["id"]].model_dump(mode="json") for a in state["candidates"]],
        "summaries": [s.model_dump(mode="json") for s in summaries],
        "limitations": limitations,
        "warnings": warnings,
    }
