"""Programmatic entry point: `run_newsletter_agent(goal)`.

    >>> from app.agent.runner import run_newsletter_agent
    >>> result = run_newsletter_agent("Create a weekly newsletter on the latest AI agent news")

By default this runs the full autonomous workflow with live Tavily + Gemini
(keys from the environment). Pass `RunOptions(deterministic=True)` for an
offline run on labelled fixture data. Human-in-the-Loop mode requires an
`approval_handler` that obtains a real decision (see app/cli.py).
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command

from app.agent.graph import build_graph, initial_state
from app.agent.services import AgentServices, build_services
from app.config import Settings, get_settings
from app.models.domain import (
    Article,
    ExecutionMode,
    ExecutionPlan,
    GoalInput,
    LogEntry,
    NewsletterDraft,
    NewsletterResult,
    ReviewResult,
    RevisionRecord,
    RunStatus,
    ToolCallRecord,
    utc_now_iso,
)
from app.services.telemetry import DeadlineReporter, RunCancelled, RunTimedOut

ApprovalHandler = Callable[[dict[str, Any]], dict[str, Any]]


@dataclass
class RunOptions:
    mode: ExecutionMode = ExecutionMode.AUTONOMOUS
    deterministic: bool = False
    topic: str | None = None
    audience: str | None = None
    article_count: int | None = None
    lookback_days: int | None = None
    approval_handler: ApprovalHandler | None = None
    echo: bool = False
    settings: Settings | None = None
    services_factory: Callable[[Any], AgentServices] | None = field(default=None, repr=False)


def approval_payload(values: dict[str, Any], kind: str) -> dict[str, Any]:
    """Data shown to a human at a gate (shared by the CLI and the API)."""
    if kind == "research":
        return {
            "kind": "research",
            "candidates": values.get("candidates", []),
            "proposed_ids": values.get("proposed_ids", []),
            "plan": values.get("plan"),
        }
    return {
        "kind": "draft",
        "draft": values.get("draft"),
        "html": values.get("html"),
        "markdown": values.get("markdown"),
        "review": values.get("review"),
        "revisions": values.get("revisions", []),
        "user_revisions": values.get("user_revisions", 0),
    }


def result_from_state(
    values: dict[str, Any], *, run_id: str, status: RunStatus | None = None, error: str | None = None
) -> NewsletterResult:
    goal = GoalInput.model_validate(values["goal_input"]) if values.get("goal_input") else None
    draft = NewsletterDraft.model_validate(values["draft"]) if values.get("draft") else None
    output = values.get("output") or {}
    status = status or RunStatus(values.get("status", "failed") if values.get("status") != "running" else "running")
    started = values.get("started_at")
    finished = values.get("finished_at") or (utc_now_iso() if status.is_terminal else None)
    duration = None
    if started and finished:
        try:
            duration = round((datetime.fromisoformat(finished) - datetime.fromisoformat(started)).total_seconds(), 2)
        except ValueError:
            duration = None
    is_test = draft.is_test_data if draft else any(Article.model_validate(a).is_test_data for a in values.get("candidates", [])[:1])
    return NewsletterResult(
        run_id=run_id,
        status=status,
        goal=goal.goal if goal else "",
        mode=goal.mode if goal else ExecutionMode.AUTONOMOUS,
        subject=draft.subject if draft else None,
        preheader=draft.preheader if draft else None,
        articles=draft.sections if draft else [],
        review=ReviewResult.model_validate(values["review"]) if values.get("review") else None,
        reviews=[ReviewResult.model_validate(r) for r in values.get("reviews", [])],
        revisions=[RevisionRecord.model_validate(r) for r in values.get("revisions", [])],
        html_path=output.get("html_path"),
        markdown_path=output.get("markdown_path"),
        html=values.get("html") if output else None,
        markdown=values.get("markdown") if output else None,
        warnings=list(values.get("warnings", [])),
        limitations=list(values.get("limitations", [])),
        plan=ExecutionPlan.model_validate(values["plan"]) if values.get("plan") else None,
        execution_log=[LogEntry.model_validate(e) for e in values.get("execution_log", [])],
        tool_calls=[ToolCallRecord.model_validate(t) for t in values.get("tool_calls", [])],
        error=error or values.get("error"),
        is_test_data=bool(is_test),
        started_at=started,
        finished_at=finished,
        duration_seconds=duration,
    )


def run_newsletter_agent(goal: str | GoalInput, options: RunOptions | None = None) -> NewsletterResult:
    """Run the complete newsletter workflow and return a validated result."""
    options = options or RunOptions()
    settings = options.settings or get_settings()
    if isinstance(goal, GoalInput):
        goal_input = goal
    else:
        goal_input = GoalInput(
            goal=goal,
            mode=options.mode,
            topic=options.topic,
            audience=options.audience,
            article_count=options.article_count,
            lookback_days=options.lookback_days,
            deterministic=options.deterministic,
        )
    if goal_input.mode == ExecutionMode.HUMAN_IN_THE_LOOP and options.approval_handler is None:
        raise ValueError(
            "Human-in-the-Loop mode needs an approval_handler that collects real user decisions "
            "(use the web UI/API or `python -m app.cli --mode hitl`)."
        )

    run_id = uuid.uuid4().hex
    reporter = DeadlineReporter(settings.max_run_seconds, echo=options.echo)
    services = (
        options.services_factory(reporter)
        if options.services_factory
        else build_services(settings, deterministic=goal_input.deterministic, reporter=reporter)
    )
    graph = build_graph(services, checkpointer=InMemorySaver())
    cfg = {"configurable": {"thread_id": run_id}, "recursion_limit": 60}
    payload: Any = initial_state(run_id, goal_input.model_dump(mode="json"), utc_now_iso())

    started = time.monotonic()
    while True:
        try:
            graph.invoke(payload, cfg)
        except (RunCancelled, RunTimedOut) as exc:
            values = graph.get_state(cfg).values
            status = RunStatus.CANCELLED if isinstance(exc, RunCancelled) else RunStatus.FAILED
            return result_from_state(values, run_id=run_id, status=status, error=str(exc))
        snapshot = graph.get_state(cfg)
        if not snapshot.interrupts:
            break
        kind = snapshot.interrupts[0].value.get("kind", "research")
        assert options.approval_handler is not None
        decision = options.approval_handler(approval_payload(snapshot.values, kind))
        payload = Command(resume=decision)
        if time.monotonic() - started > settings.max_run_seconds * 20:
            break  # safety net against a handler that loops forever

    values = graph.get_state(cfg).values
    return result_from_state(values, run_id=run_id)
