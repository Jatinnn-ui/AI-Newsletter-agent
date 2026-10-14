"""Typed request/response models for the public API."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

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
)


class StartRunRequest(GoalInput):
    """POST /api/agent/runs body (same fields as GoalInput)."""


class ApproveResearchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    selected_ids: list[str] | None = Field(
        default=None, max_length=7, description="Article ids to include. Omit to accept the proposal."
    )


class ReviseRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    feedback: str | None = Field(default=None, max_length=1000)


class HealthResponse(BaseModel):
    status: Literal["ok"]
    version: str
    time: str
    config: dict[str, Any]
    runs: dict[str, int]


class RunSummary(BaseModel):
    run_id: str
    status: RunStatus
    mode: ExecutionMode
    deterministic: bool
    goal: str
    current_stage: str | None = None
    created_at: str
    updated_at: str
    error: str | None = None


class ApprovalInfo(BaseModel):
    kind: Literal["research", "draft"]
    requested_at: str
    user_revisions_used: int = 0
    user_revisions_max: int = 0


class RunMetrics(BaseModel):
    duration_seconds: float | None = None
    article_count: int = 0
    candidate_count: int = 0
    tool_call_count: int = 0
    review_score: int | None = None
    review_passed: bool | None = None
    revision_count: int = 0


class RunDetail(BaseModel):
    run_id: str
    status: RunStatus
    mode: ExecutionMode
    deterministic: bool
    goal: str
    request: dict[str, Any]
    current_stage: str | None = None
    stages: dict[str, str]
    created_at: str
    updated_at: str
    error: str | None = None
    approval: ApprovalInfo | None = None
    plan: ExecutionPlan | None = None
    candidates: list[Article] = Field(default_factory=list)
    proposed_ids: list[str] = Field(default_factory=list)
    selected_ids: list[str] = Field(default_factory=list)
    draft: NewsletterDraft | None = None
    html: str | None = None
    markdown: str | None = None
    review: ReviewResult | None = None
    reviews: list[ReviewResult] = Field(default_factory=list)
    revisions: list[RevisionRecord] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    output: dict[str, Any] | None = None
    logs: list[LogEntry] = Field(default_factory=list)
    tool_calls: list[ToolCallRecord] = Field(default_factory=list)
    metrics: RunMetrics
    delivery_mode: Literal["simulated"] = "simulated"
    last_event_id: int = 0


class ErrorResponse(BaseModel):
    detail: Any


__all__ = [
    "StartRunRequest", "ApproveResearchRequest", "ReviseRequest", "HealthResponse", "RunSummary", "RunDetail",
    "ApprovalInfo", "RunMetrics", "NewsletterResult", "ErrorResponse",
]
