"""15. Autonomous completion  16. HITL pause/approval  17. Revision request + cancellation (graph level)"""

import pytest
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command

from app.agent.graph import build_graph, initial_state
from app.agent.runner import RunOptions, run_newsletter_agent
from app.models.domain import ExecutionMode, GoalInput, RunStatus, utc_now_iso
from app.services.telemetry import RunCancelled
from app.tools.web_search import FixtureSearchProvider
from tests.conftest import GOAL


def test_autonomous_run_completes_without_approvals(make_services):
    result = run_newsletter_agent(GOAL, RunOptions(deterministic=True, services_factory=make_services))
    assert result.status == RunStatus.COMPLETED
    assert 5 <= len(result.articles) <= 7
    assert result.is_test_data and all(a.source_url.startswith("https://example.") for a in result.articles)
    assert result.plan and result.plan.research_queries
    stages = {e.stage for e in result.execution_log}
    assert {"planning", "research", "selection", "summarization", "writing", "review", "output"} <= stages
    tools = {t.tool.split(" ")[0] for t in result.tool_calls}
    assert {"web_search", "article_retrieval", "newsletter_renderer.render", "newsletter_storage.save"} <= tools
    assert all(t.ended_at and t.started_at for t in result.tool_calls)
    assert result.review and result.review.passed


def test_default_signature_is_one_argument():
    import inspect

    sig = inspect.signature(run_newsletter_agent)
    assert list(sig.parameters)[0] == "goal" and sig.parameters["options"].default is None


def test_search_failure_is_reported_with_recovery(make_services):
    result = run_newsletter_agent(
        GOAL, RunOptions(deterministic=True, services_factory=lambda r: make_services(r, search=FixtureSearchProvider(fail=True)))
    )
    assert result.status == RunStatus.FAILED
    assert "could not be reached" in result.error and not result.articles


def test_hitl_requires_handler():
    with pytest.raises(ValueError):
        run_newsletter_agent(GOAL, RunOptions(mode=ExecutionMode.HUMAN_IN_THE_LOOP, deterministic=True))


def _hitl_graph(make_services):
    graph = build_graph(make_services(), checkpointer=InMemorySaver())
    goal = GoalInput(goal=GOAL, mode=ExecutionMode.HUMAN_IN_THE_LOOP, deterministic=True)
    cfg = {"configurable": {"thread_id": "t1"}}
    graph.invoke(initial_state("t1" * 16, goal.model_dump(mode="json"), utc_now_iso()), cfg)
    return graph, cfg


def test_hitl_pauses_and_respects_user_selection(make_services):
    graph, cfg = _hitl_graph(make_services)
    snap = graph.get_state(cfg)
    assert snap.interrupts and snap.interrupts[0].value["kind"] == "research"
    assert "draft" not in snap.values  # nothing written before approval

    chosen = [c["id"] for c in snap.values["candidates"]][-3:]
    graph.invoke(Command(resume={"action": "approve", "selected_ids": chosen}), cfg)
    snap = graph.get_state(cfg)
    assert snap.interrupts[0].value["kind"] == "draft"
    assert [s["article_id"] for s in snap.values["draft"]["sections"]] == [i for i in chosen]
    assert "output" not in snap.values  # not saved before draft approval

    graph.invoke(Command(resume={"action": "approve"}), cfg)
    final = graph.get_state(cfg)
    assert not final.interrupts and final.values["status"] in ("completed", "completed_with_warnings")
    assert final.values["output"]["html_path"].endswith(".html")
    kinds = [d["kind"] + ":" + d["action"] for d in final.values["human_decisions"]]
    assert kinds == ["research:approve", "draft:approve"]


def test_hitl_revision_request_reruns_revision_and_review(make_services):
    graph, cfg = _hitl_graph(make_services)
    graph.invoke(Command(resume={"action": "approve", "selected_ids": None}), cfg)
    before = graph.get_state(cfg).values
    graph.invoke(Command(resume={"action": "revise", "feedback": "Make the summaries shorter"}), cfg)
    snap = graph.get_state(cfg)
    assert snap.interrupts[0].value["kind"] == "draft"  # back to the human, not auto-saved
    rev = snap.values["revisions"][-1]
    assert rev["trigger"] == "user" and rev["feedback"] == "Make the summaries shorter"
    assert len(snap.values["reviews"]) == len(before["reviews"]) + 1
    assert snap.values["draft"]["version"] == before["draft"]["version"] + 1
    assert snap.values["user_revisions"] == 1


def test_cancellation_stops_workflow(make_services):
    class CancelAfterPlanning:
        def __init__(self):
            self.calls = 0

        def emit(self, *a):
            pass

        def check_cancelled(self, run_id):
            self.calls += 1
            if self.calls > 1:
                raise RunCancelled("cancelled")

    reporter = CancelAfterPlanning()
    result = run_newsletter_agent(GOAL, RunOptions(deterministic=True, services_factory=lambda r: make_services(reporter)))
    assert result.status == RunStatus.CANCELLED
    assert result.html_path is None
