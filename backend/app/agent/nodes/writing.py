"""Node D: Newsletter writer (editorial copy + HTML/Markdown rendering)."""

from __future__ import annotations

from app.agent.llm_tasks import DeterministicAgentLLM, Editorial
from app.agent.nodes.base import agent_node, articles_by_id, llm_reason
from app.agent.services import AgentServices
from app.agent.state import AgentState
from app.models.domain import Article, ArticleSummary, ExecutionPlan, NewsletterDraft, NewsletterSection, utc_now_iso
from app.services.telemetry import NodeContext
from app.tools.newsletter_renderer import render_newsletter


def build_section(article: Article, summary: ArticleSummary) -> NewsletterSection:
    """Source metadata always comes from the research record, never from the LLM."""
    return NewsletterSection(
        article_id=article.id,
        headline=article.title,
        summary=summary.summary,
        why_it_matters=summary.why_it_matters,
        key_facts=summary.key_facts,
        source_url=article.url,
        publisher=article.publisher,
        published_date=article.published_date,
        date_source=article.date_source,
        content_basis=article.content_basis,
    )


def render_into_state(draft: NewsletterDraft, ctx: NodeContext) -> dict:
    with ctx.track("newsletter_renderer.render", f"draft v{draft.version}, {len(draft.sections)} sections") as h:
        rendered = render_newsletter(draft)
        v = rendered.validation
        if v.valid:
            h.success(f"HTML {len(rendered.html)} bytes, Markdown {len(rendered.markdown)} bytes, {len(v.links)} links; valid")
        else:
            h.fail("; ".join(v.errors[:3]), "HTML validation failed")
    return {
        "draft": draft.model_dump(mode="json"),
        "html": rendered.html,
        "markdown": rendered.markdown,
        "html_validation": rendered.validation.model_dump(mode="json"),
    }


@agent_node("writing")
def writer_node(state: AgentState, ctx: NodeContext, svc: AgentServices) -> dict:
    cfg = ExecutionPlan.model_validate(state["plan"]).config
    by_id = articles_by_id(state)
    summaries = [ArticleSummary.model_validate(s) for s in state["summaries"]]
    articles = [by_id[s.article_id] for s in summaries if s.article_id in by_id]
    limitations = list(state.get("limitations", []))
    warnings = list(state.get("warnings", []))

    with ctx.track(f"llm.editorial ({svc.llm.name})", f"{len(summaries)} stories, topic={cfg.topic}") as h:
        try:
            editorial: Editorial = svc.llm.write_editorial(cfg, summaries, articles, limitations)
            h.success(f"subject: {editorial.subject[:80]}")
        except Exception as exc:
            editorial = DeterministicAgentLLM().write_editorial(cfg, summaries, articles, limitations)
            h.fallback("LLM editorial failed; template copy used.", str(exc))
            warnings.append(f"{llm_reason(exc)}, so the subject line and intro use a fixed template.")
            ctx.log(f"Editorial LLM unavailable ({type(exc).__name__}); using template copy.", "warning")

    draft = NewsletterDraft(
        subject=editorial.subject.strip(),
        preheader=editorial.preheader.strip(),
        title=(editorial.title.strip() or cfg.title_hint),
        intro=editorial.intro.strip(),
        sections=[build_section(by_id[s.article_id], s) for s in summaries if s.article_id in by_id],
        closing=editorial.closing.strip(),
        generated_at=utc_now_iso(),
        limitations=limitations,
        is_test_data=any(a.is_test_data for a in articles),
        version=1,
    )
    update = render_into_state(draft, ctx)
    ctx.log(f"Draft written: \"{draft.subject}\" with {len(draft.sections)} stories.", "success")
    ctx.artifact("draft", {"draft": update["draft"], "html": update["html"], "markdown": update["markdown"]})
    return {**update, "warnings": warnings}
