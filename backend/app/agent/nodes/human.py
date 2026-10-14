"""Human-in-the-Loop gates.

Each gate calls LangGraph `interrupt()`, which persists the run in the
checkpointer and stops execution until the API resumes it with
`Command(resume=decision)`. Nothing is auto-approved: the only way past a
gate is an explicit decision supplied by a user.

Gates re-execute from the top when resumed, so nothing with side effects
happens before `interrupt()`.
"""

from __future__ import annotations

from typing import Callable

from langgraph.types import interrupt

from app.agent.services import AgentServices
from app.agent.state import AgentState
from app.models.domain import HumanDecision
from app.services.telemetry import NodeContext

MAX_SELECTED = 7


def make_research_gate(svc: AgentServices) -> Callable[[AgentState], dict]:
    def research_gate(state: AgentState) -> dict:
        decision = interrupt({"kind": "research", "proposed_ids": state.get("proposed_ids", [])})
        ctx = NodeContext(run_id=state["run_id"], stage="selection", reporter=svc.reporter)
        ctx.check_cancelled()
        valid = {c["id"] for c in state.get("candidates", [])}
        requested = decision.get("selected_ids") if isinstance(decision, dict) else None
        ids = [i for i in dict.fromkeys(requested or []) if i in valid][:MAX_SELECTED]
        if not ids:
            ids = list(state.get("proposed_ids", []))
        proposed = set(state.get("proposed_ids", []))
        removed = len(proposed - set(ids))
        added = len(set(ids) - proposed)
        ctx.log(
            f"User approved {len(ids)} article(s)"
            + (f" ({removed} removed, {added} added vs. the proposal)." if removed or added else " as proposed."),
            "success",
        )
        record = HumanDecision(kind="research", action="approve", selected_ids=ids)
        return {
            "selected_ids": ids,
            "human_decisions": list(state.get("human_decisions", [])) + [record.model_dump(mode="json")],
            **ctx.flush(),
        }

    return research_gate


def make_draft_gate(svc: AgentServices) -> Callable[[AgentState], dict]:
    def draft_gate(state: AgentState) -> dict:
        decision = interrupt({"kind": "draft", "version": state.get("draft", {}).get("version")})
        ctx = NodeContext(run_id=state["run_id"], stage="output", reporter=svc.reporter)
        ctx.check_cancelled()
        action = decision.get("action") if isinstance(decision, dict) else None
        decisions = list(state.get("human_decisions", []))
        if action == "revise":
            feedback = (decision.get("feedback") or "").strip()[:1000] or "Improve clarity and accuracy."
            ctx.log(f"User requested a revision: \"{feedback[:160]}\"", "info")
            decisions.append(HumanDecision(kind="draft", action="revise", feedback=feedback).model_dump(mode="json"))
            return {
                "draft_decision": "revise",
                "pending_feedback": feedback,
                "user_revisions": state.get("user_revisions", 0) + 1,
                "human_decisions": decisions,
                **ctx.flush(),
            }
        ctx.log("User approved the newsletter draft.", "success")
        decisions.append(HumanDecision(kind="draft", action="approve").model_dump(mode="json"))
        return {"draft_decision": "approve", "human_decisions": decisions, **ctx.flush()}

    return draft_gate
