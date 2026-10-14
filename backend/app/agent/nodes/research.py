"""Node B: Research agent (search → normalize → dedupe → rank → retrieve → propose)."""

from __future__ import annotations

from datetime import timedelta

from app.agent.nodes.base import WorkflowError, agent_node
from app.agent.services import AgentServices
from app.agent.state import AgentState
from app.models.domain import Article, ExecutionPlan
from app.services.ranking import dedupe_by_url, dedupe_stories, score_articles, select_articles, topic_terms
from app.services.telemetry import NodeContext
from app.tools.article_retrieval import normalize_search_results
from app.tools.web_search import SearchAuthError, SearchError, SearchResult

MAX_CANDIDATES = 15


def retrieve_articles(articles: list[Article], ctx: NodeContext, svc: AgentServices) -> list[Article]:
    """Run Tool 2 on each article, recording every call. Never raises for page failures."""
    out = []
    for art in articles:
        ctx.check_cancelled()
        with ctx.track("article_retrieval", art.url[:200]) as h:
            updated = svc.retrieval.retrieve(art, today=svc.today())
            if updated.content_basis == "full_text":
                h.success(updated.retrieval_note or "retrieved")
            else:
                h.fallback(updated.retrieval_note or "using search snippet")
        out.append(updated)
    return out


@agent_node("research")
def research_node(state: AgentState, ctx: NodeContext, svc: AgentServices) -> dict:
    plan = ExecutionPlan.model_validate(state["plan"])
    cfg = plan.config
    today = svc.today()
    start = today - timedelta(days=cfg.lookback_days)
    settings = svc.settings
    warnings = list(state.get("warnings", []))
    if svc.deterministic:
        ctx.log("Deterministic test mode: using labelled fixture search data (not real news).", "warning")

    raw: list[SearchResult] = []
    failures: list[SearchError] = []
    for query in plan.research_queries:
        ctx.check_cancelled()
        with ctx.track(f"web_search ({svc.search.name})", f'"{query}" since {start.isoformat()}') as h:
            try:
                results = svc.search.search(query, start_date=start, max_results=settings.search_max_results_per_query)
            except SearchAuthError:
                raise
            except SearchError as exc:
                failures.append(exc)
                h.fail(str(exc))
                ctx.log(f"Search failed for \"{query}\": {exc}", "warning")
                continue
            h.success(f"{len(results)} result(s)")
        ctx.log(f"Search \"{query}\" returned {len(results)} result(s).", "info")
        raw.extend(results)

    if not raw:
        if failures:
            raise failures[0]
        raise WorkflowError(
            "The search provider returned no results for any query. Try a broader topic or a longer lookback period."
        )
    if failures:
        warnings.append(f"{len(failures)} of {len(plan.research_queries)} search queries failed; results may be incomplete.")

    with ctx.track("article_normalizer", f"{len(raw)} raw results") as h:
        normalized, skipped = normalize_search_results(raw, today=today)
        unique, url_dupes = dedupe_by_url(normalized)
        h.success(f"{len(normalized)} normalized, {url_dupes} duplicate URL(s) removed, {len(skipped)} skipped")
    ctx.log(f"Normalized {len(normalized)} results; removed {url_dupes} duplicate URL(s).", "info")

    terms = topic_terms(cfg.topic)
    scored, notes = score_articles(unique, terms=terms, today=today, lookback_days=cfg.lookback_days)
    kept, story_dupes = dedupe_stories(scored)
    if story_dupes:
        ctx.log(f"Filtered {len(story_dupes)} article(s) covering an already-included story.", "info")
    for note in notes[:6]:
        ctx.log(note, "info")

    to_retrieve = kept[: settings.retrieval_max_articles]
    retrieved = retrieve_articles(to_retrieve, ctx, svc) + kept[settings.retrieval_max_articles:]
    full = sum(1 for a in retrieved if a.content_basis == "full_text")
    ctx.log(f"Retrieved full text for {full} of {len(to_retrieve)} article(s); others use search snippets.", "info")

    # Re-score: retrieval may have corrected dates or added text.
    ranked, late_notes = score_articles(retrieved, terms=terms, today=today, lookback_days=cfg.lookback_days)
    for note in late_notes[:4]:
        ctx.log(note, "info")
    ranked = ranked[:MAX_CANDIDATES]
    if not ranked:
        raise WorkflowError(
            f"No relevant articles were found within the last {cfg.lookback_days} days. "
            "Try a broader topic or a longer lookback period."
        )

    proposed, select_notes = select_articles(ranked, cfg.article_count)
    undated = sum(1 for a in proposed if not a.published_date)
    if undated:
        ctx.log(f"{undated} proposed article(s) have no verifiable publication date.", "warning")
    for note in select_notes:
        ctx.log(note, "warning")

    ctx.log(
        f"Research complete: {len(ranked)} candidate(s), {len(proposed)} proposed for the newsletter.",
        "success",
    )
    candidates = [a.model_dump(mode="json") for a in ranked]
    proposed_ids = [a.id for a in proposed]
    ctx.artifact("candidates", {"candidates": candidates, "proposed_ids": proposed_ids})
    return {
        "candidates": candidates,
        "proposed_ids": proposed_ids,
        "research_notes": select_notes + skipped[:3],
        "warnings": warnings,
    }
