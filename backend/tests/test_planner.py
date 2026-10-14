"""1. Goal validation  2. Planner output validation"""

import pytest
from pydantic import ValidationError

from app.agent.llm_tasks import PlanRefinement
from app.agent.planner import build_plan, heuristic_config
from app.models.domain import ExecutionMode, ExecutionPlan, GoalInput, Stage
from tests.conftest import GOAL


@pytest.mark.parametrize("bad", ["", "   ", "short", "12345 67890 !!!", None, 42])
def test_invalid_goals_are_rejected(bad):
    with pytest.raises(ValidationError):
        GoalInput(goal=bad)


def test_goal_is_cleaned_and_limits_enforced():
    g = GoalInput(goal="  Create a\x00 newsletter   on robotics  ")
    assert g.goal == "Create a newsletter on robotics"
    with pytest.raises(ValidationError):
        GoalInput(goal=GOAL, article_count=12)
    with pytest.raises(ValidationError):
        GoalInput(goal=GOAL, lookback_days=0)
    with pytest.raises(ValidationError):
        GoalInput(goal=GOAL, unknown_field=True)


def test_heuristic_config_extracts_topic_window_and_defaults():
    cfg, assumptions = heuristic_config(GoalInput(goal=GOAL))
    assert cfg.topic.lower() == "ai agent"
    assert cfg.lookback_days == 7  # "weekly"
    assert cfg.article_count == 5
    assert "subscribers" in cfg.audience
    assert any("article count" in a for a in assumptions)


def test_explicit_settings_override_goal():
    goal = GoalInput(goal="Create a daily newsletter about robotics startups", topic="humanoid robots",
                     article_count=6, lookback_days=3, audience="investors")
    cfg, _ = heuristic_config(goal)
    assert (cfg.topic, cfg.article_count, cfg.lookback_days, cfg.audience) == ("humanoid robots", 6, 3, "investors")


def test_count_and_window_parsed_from_goal():
    cfg, _ = heuristic_config(GoalInput(goal="Summarize the top 7 articles on quantum computing from the last 14 days"))
    assert cfg.article_count == 7 and cfg.lookback_days == 14


def test_plan_structure_and_llm_refinement_respects_user_values():
    goal = GoalInput(goal=GOAL, topic="AI agents", mode=ExecutionMode.HUMAN_IN_THE_LOOP)
    cfg, assumptions = heuristic_config(goal)
    refinement = PlanRefinement(
        topic="something else", audience="ML engineers", title_hint="Agent Brief", lookback_days=99,
        article_count=6, research_queries=["AI agents news", "AI agents news", "agentic AI enterprise"],
    )
    plan = build_plan(goal, cfg, assumptions, refinement, "llm", max_queries=4)
    ExecutionPlan.model_validate(plan.model_dump())
    assert plan.config.topic == "AI agents"  # explicit user topic wins
    assert plan.config.audience == "ML engineers"
    assert plan.config.lookback_days == 7  # out-of-range LLM value ignored
    assert plan.config.article_count == 6
    assert plan.research_queries == ["AI agents news", "agentic AI enterprise"]  # deduplicated
    stages = [t.stage for t in plan.tasks]
    assert stages[0] == Stage.PLANNING and Stage.OUTPUT in stages
    assert any("Human approval" in t.title for t in plan.tasks)
