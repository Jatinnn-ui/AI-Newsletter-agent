"""Node A: Goal interpreter and planner."""

from __future__ import annotations

from app.agent.nodes.base import agent_node, llm_reason
from app.agent.planner import build_plan, heuristic_config
from app.agent.services import AgentServices
from app.agent.state import AgentState
from app.models.domain import GoalInput
from app.services.telemetry import NodeContext


@agent_node("planning")
def planner_node(state: AgentState, ctx: NodeContext, svc: AgentServices) -> dict:
    goal = GoalInput.model_validate(state["goal_input"])  # raises ValueError for invalid goals
    ctx.log(f"Interpreting goal: \"{goal.goal[:160]}\"", "running")
    config, assumptions = heuristic_config(goal)
    warnings = list(state.get("warnings", []))

    refinement = None
    planner = "deterministic" if svc.deterministic else "llm"
    with ctx.track(f"llm.plan ({svc.llm.name})", f"goal ({len(goal.goal)} chars), topic={config.topic}") as h:
        try:
            refinement = svc.llm.refine_plan(goal, config)
            h.success(f"{len(refinement.research_queries)} queries; topic='{refinement.topic[:60]}'")
        except Exception as exc:
            planner = "heuristic_fallback"
            h.fallback("LLM planning failed; used heuristic plan.", str(exc))
            warnings.append(f"{llm_reason(exc)}, so the plan was made with simple rules instead of AI.")
            ctx.log(f"LLM planning unavailable ({type(exc).__name__}); using heuristic plan.", "warning")

    plan = build_plan(goal, config, assumptions, refinement, planner, svc.settings.search_max_queries)
    c = plan.config
    ctx.log(
        f"Plan ready: topic '{c.topic}', audience '{c.audience}', {c.article_count} stories, "
        f"{c.lookback_days}-day window, {len(plan.research_queries)} queries.",
        "success",
        queries=plan.research_queries,
    )
    for a in plan.assumptions:
        ctx.log(f"Assumption: {a}", "info")
    dumped = plan.model_dump(mode="json")
    ctx.artifact("plan", dumped)
    return {"plan": dumped, "warnings": warnings, "status": "running"}
