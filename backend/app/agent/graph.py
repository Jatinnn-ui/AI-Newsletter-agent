"""LangGraph workflow definition.

    planner → research ─┬──────────────────────────→ summarize → writer → critic ─┬→ revision → critic (≤2 auto)
                        └→ research_gate (HITL) ──→┘                              ├→ draft_gate (HITL) ─┬→ output
                                                                                  │                     └→ revision
                                                                                  └→ output → END
Any node that sets status="failed" routes straight to END.
"""

from __future__ import annotations

from langgraph.graph import END, START, StateGraph

from app.agent.nodes.human import make_draft_gate, make_research_gate
from app.agent.nodes.output import output_node
from app.agent.nodes.planning import planner_node
from app.agent.nodes.research import research_node
from app.agent.nodes.review import critic_node, revision_node
from app.agent.nodes.summarize import summarize_node
from app.agent.nodes.writing import writer_node
from app.agent.services import AgentServices
from app.agent.state import AgentState
from app.models.domain import ExecutionMode, ReviewResult

HITL = ExecutionMode.HUMAN_IN_THE_LOOP.value


def _failed(state: AgentState) -> bool:
    return state.get("status") == "failed"


def build_graph(services: AgentServices, checkpointer=None):
    max_revisions = services.settings.max_revisions

    def after_simple(next_node: str):
        def route(state: AgentState) -> str:
            return END if _failed(state) else next_node
        return route

    def after_research(state: AgentState) -> str:
        if _failed(state):
            return END
        return "research_gate" if state.get("mode") == HITL else "summarize"

    def after_critic(state: AgentState) -> str:
        if _failed(state):
            return END
        review = ReviewResult.model_validate(state["review"])
        if review.revision_required and state.get("critic_revisions", 0) < max_revisions:
            return "revision"
        return "draft_gate" if state.get("mode") == HITL else "output"

    def after_draft_gate(state: AgentState) -> str:
        return "revision" if state.get("draft_decision") == "revise" else "output"

    g = StateGraph(AgentState)
    g.add_node("planner", planner_node(services))
    g.add_node("research", research_node(services))
    g.add_node("research_gate", make_research_gate(services))
    g.add_node("summarize", summarize_node(services))
    g.add_node("writer", writer_node(services))
    g.add_node("critic", critic_node(services))
    g.add_node("revision", revision_node(services))
    g.add_node("draft_gate", make_draft_gate(services))
    g.add_node("output", output_node(services))

    g.add_edge(START, "planner")
    g.add_conditional_edges("planner", after_simple("research"), ["research", END])
    g.add_conditional_edges("research", after_research, ["research_gate", "summarize", END])
    g.add_edge("research_gate", "summarize")
    g.add_conditional_edges("summarize", after_simple("writer"), ["writer", END])
    g.add_conditional_edges("writer", after_simple("critic"), ["critic", END])
    g.add_conditional_edges("critic", after_critic, ["revision", "draft_gate", "output", END])
    g.add_conditional_edges("revision", after_simple("critic"), ["critic", END])
    g.add_conditional_edges("draft_gate", after_draft_gate, ["revision", "output"])
    g.add_edge("output", END)
    return g.compile(checkpointer=checkpointer)


def initial_state(run_id: str, goal_input: dict, started_at: str) -> AgentState:
    return {
        "run_id": run_id,
        "goal_input": goal_input,
        "mode": goal_input.get("mode", "autonomous"),
        "started_at": started_at,
        "status": "running",
        "warnings": [],
        "reviews": [],
        "revisions": [],
        "critic_revisions": 0,
        "user_revisions": 0,
        "human_decisions": [],
        "pending_feedback": None,
        "draft_decision": None,
        "execution_log": [],
        "tool_calls": [],
    }
