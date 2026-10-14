"""Node E (critic) and Node F (revision)."""

from __future__ import annotations

from app.agent.critic import review_draft
from app.agent.nodes.base import agent_node, articles_by_id
from app.agent.nodes.writing import render_into_state
from app.agent.services import AgentServices
from app.agent.state import AgentState
from app.models.domain import ExecutionPlan, GoalInput, NewsletterDraft, ReviewResult, RevisionRecord
from app.services.telemetry import NodeContext
from app.tools.newsletter_renderer import HtmlValidation


@agent_node("review")
def critic_node(state: AgentState, ctx: NodeContext, svc: AgentServices) -> dict:
    goal = GoalInput.model_validate(state["goal_input"])
    cfg = ExecutionPlan.model_validate(state["plan"]).config
    draft = NewsletterDraft.model_validate(state["draft"])
    by_id = articles_by_id(state)
    validation = HtmlValidation.model_validate(state["html_validation"])
    reviews = list(state.get("reviews", []))
    attempt = len(reviews) + 1

    llm_critique, llm_error = None, None
    with ctx.track(f"llm.critique ({svc.llm.name})", f"draft v{draft.version}, {len(draft.sections)} stories") as h:
        try:
            llm_critique = svc.llm.critique(goal.goal, draft, [by_id[s.article_id] for s in draft.sections if s.article_id in by_id])
            h.success(
                f"goal {llm_critique.goal_alignment}, coherence {llm_critique.coherence}, "
                f"{len(llm_critique.unsupported_claims)} unsupported claim(s)"
            )
        except Exception as exc:
            llm_error = type(exc).__name__
            h.fallback("LLM critique unavailable; rule-based checks only.", str(exc))
            ctx.log("LLM critique unavailable; continuing with rule-based checks only.", "warning")

    with ctx.track("quality_checks", f"10 checks, threshold {svc.settings.review_pass_threshold}") as h:
        review = review_draft(
            goal=goal.goal,
            topic=cfg.topic,
            requested_count=cfg.article_count,
            draft=draft,
            articles=by_id,
            validation=validation,
            llm=llm_critique,
            attempt=attempt,
            threshold=svc.settings.review_pass_threshold,
            today=svc.today(),
            llm_error=llm_error,
        )
        h.success(f"score {review.score}/100, passed={review.passed}, {len(review.issues)} issue(s)")

    level = "success" if review.passed and not review.revision_required else "warning"
    ctx.log(f"Review #{attempt}: {review.summary}", level, score=review.score)
    for issue in review.issues:
        if issue.severity in ("critical", "major"):
            ctx.log(f"[{issue.severity}] {issue.message}", "warning")

    revisions = list(state.get("revisions", []))
    if revisions and revisions[-1].get("score_after") is None:
        revisions[-1] = {**revisions[-1], "score_after": review.score}
    dumped = review.model_dump(mode="json")
    ctx.artifact("review", dumped)
    return {"review": dumped, "reviews": reviews + [dumped], "revisions": revisions}


@agent_node("revision")
def revision_node(state: AgentState, ctx: NodeContext, svc: AgentServices) -> dict:
    draft = NewsletterDraft.model_validate(state["draft"])
    review = ReviewResult.model_validate(state["review"])
    by_id = articles_by_id(state)
    feedback = state.get("pending_feedback")
    trigger = "user" if feedback else "critic"
    revisions = list(state.get("revisions", []))
    attempt = len(revisions) + 1

    issues = [i for i in review.issues if i.correctable]
    issue_texts = [f"[{i.severity}] {i.message} -> {i.suggestion}" for i in issues]
    ctx.log(
        f"Revision #{attempt} ({'user feedback' if trigger == 'user' else 'critic'}): addressing {len(issues)} issue(s).",
        "running",
    )
    changes: list[str] = []
    with ctx.track(f"llm.revise ({svc.llm.name})", f"{len(issues)} issue(s); feedback={'yes' if feedback else 'no'}") as h:
        try:
            out = svc.llm.revise(draft, [by_id[s.article_id] for s in draft.sections if s.article_id in by_id],
                                 issue_texts, feedback)
            revised = {s.article_id: s for s in out.sections}
            new_sections = []
            for s in draft.sections:
                r = revised.get(s.article_id)
                if r is None:
                    new_sections.append(s)
                    continue
                new_sections.append(
                    s.model_copy(update={
                        "summary": r.summary.strip() or s.summary,
                        "why_it_matters": r.why_it_matters.strip() or s.why_it_matters,
                        "key_facts": [f.strip() for f in r.key_facts if f.strip()][:3],
                    })
                )
            draft = draft.model_copy(update={
                "subject": out.subject.strip() or draft.subject,
                "preheader": out.preheader.strip() or draft.preheader,
                "intro": out.intro.strip() or draft.intro,
                "closing": out.closing.strip() or draft.closing,
                "sections": new_sections,
                "version": draft.version + 1,
            })
            changes = out.changes[:8] or ["Revised copy to address review issues."]
            h.success(f"{len(changes)} change(s)")
        except Exception as exc:
            h.fail(str(exc), "Revision failed; draft unchanged")
            changes = [f"Revision attempt failed ({type(exc).__name__}); the previous draft was kept."]
            ctx.log(changes[0], "warning")

    if len(draft.subject) > 90:
        draft.subject = draft.subject[:87].rsplit(" ", 1)[0] + "…"
        changes.append("Shortened the subject line.")

    record = RevisionRecord(
        attempt=attempt,
        trigger=trigger,
        feedback=feedback,
        issues_addressed=[i.id for i in issues],
        changes=changes,
        score_before=review.score,
    )
    for c in changes:
        ctx.log(f"Change: {c}", "info")
    update = render_into_state(draft, ctx)
    ctx.artifact("draft", {"draft": update["draft"], "html": update["html"], "markdown": update["markdown"]})
    return {
        **update,
        "revisions": revisions + [record.model_dump(mode="json")],
        "critic_revisions": state.get("critic_revisions", 0) + (1 if trigger == "critic" else 0),
        "pending_feedback": None,
        "draft_decision": None,
    }
