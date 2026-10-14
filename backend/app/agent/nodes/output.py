"""Node G: Output and simulated delivery."""

from __future__ import annotations

from app.agent.nodes.base import WorkflowError, agent_node
from app.agent.services import AgentServices
from app.agent.state import AgentState
from app.models.domain import NewsletterDraft, ReviewResult, RunStatus, utc_now_iso
from app.services.telemetry import NodeContext
from app.tools.newsletter_renderer import HtmlValidation, RenderedNewsletter, save_newsletter


@agent_node("output")
def output_node(state: AgentState, ctx: NodeContext, svc: AgentServices) -> dict:
    draft = NewsletterDraft.model_validate(state["draft"])
    review = ReviewResult.model_validate(state["review"])
    validation = HtmlValidation.model_validate(state["html_validation"])
    if not validation.valid:
        raise WorkflowError("Cannot save: the rendered HTML failed validation (" + "; ".join(validation.errors[:2]) + ").")

    rendered = RenderedNewsletter(html=state["html"], markdown=state["markdown"], validation=validation)
    with ctx.track("newsletter_storage.save", f"run {state['run_id'][:8]}, '{draft.title[:50]}'") as h:
        saved = save_newsletter(rendered, run_id=state["run_id"], title=draft.title, storage=svc.storage)
        h.success(f"{saved.html_filename}, {saved.markdown_filename}")

    warnings = list(state.get("warnings", []))
    blocking = [i for i in review.issues if i.severity in ("critical", "major")]
    n_rev = len(state.get("revisions", []))
    if review.passed and not blocking:
        status = RunStatus.COMPLETED
    else:
        status = RunStatus.COMPLETED_WITH_WARNINGS
        verdict = (
            f"Final review did not pass ({review.score}/100, threshold {review.threshold})"
            if not review.passed
            else f"Final review passed ({review.score}/100) but major issues remain"
        )
        warnings.append(f"{verdict} after {n_rev} revision(s). Unresolved: " + "; ".join(i.message for i in blocking[:4]))
        ctx.log("Saved with warnings: unresolved review issues remain. Check them before using.", "warning")

    if not state.get("revisions"):
        ctx.stage_event("skipped", "No revision was required.", stage="revision")
    ctx.log(f"Saved HTML to {saved.html_filename} and Markdown to {saved.markdown_filename}.", "success")
    ctx.log(
        f"Simulated delivery: subject \"{draft.subject}\". No email was sent; the newsletter was saved to files only.",
        "success",
    )
    return {
        "output": saved.model_dump(mode="json"),
        "status": status.value,
        "warnings": warnings,
        "finished_at": utc_now_iso(),
    }
