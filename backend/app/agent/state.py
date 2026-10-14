"""Typed LangGraph state for the newsletter workflow.

Values are JSON-compatible dicts (Pydantic `model_dump(mode="json")`) so the
SQLite checkpointer can persist paused Human-in-the-Loop runs.
Only the log and tool-call lists use an append reducer; every other key is
replaced by the node that writes it.
"""

from __future__ import annotations

import operator
from typing import Annotated, Any, TypedDict


class AgentState(TypedDict, total=False):
    run_id: str
    goal_input: dict[str, Any]
    mode: str
    started_at: str

    # Planner
    plan: dict[str, Any]

    # Research
    candidates: list[dict[str, Any]]
    proposed_ids: list[str]
    research_notes: list[str]
    limitations: list[str]

    # Selection + summarization
    selected_ids: list[str]
    summaries: list[dict[str, Any]]

    # Writing / rendering
    draft: dict[str, Any]
    html: str
    markdown: str
    html_validation: dict[str, Any]

    # Review / revision
    review: dict[str, Any]
    reviews: list[dict[str, Any]]
    revisions: list[dict[str, Any]]
    critic_revisions: int
    user_revisions: int
    pending_feedback: str | None
    draft_decision: str | None  # "approve" | "revise" | None
    human_decisions: list[dict[str, Any]]

    # Output
    output: dict[str, Any]
    warnings: list[str]
    status: str
    error: str | None
    finished_at: str

    # Observability (append-only)
    execution_log: Annotated[list[dict[str, Any]], operator.add]
    tool_calls: Annotated[list[dict[str, Any]], operator.add]
