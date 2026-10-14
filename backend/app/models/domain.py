"""Validated domain models shared by the agent, tools and API.

LangGraph state stores these models as plain JSON-compatible dicts
(`model_dump(mode="json")`) so checkpoints stay portable; nodes re-validate
them with these classes when reading state.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def utc_now_iso() -> str:
    return utc_now().isoformat(timespec="milliseconds")


class ExecutionMode(str, Enum):
    AUTONOMOUS = "autonomous"
    HUMAN_IN_THE_LOOP = "human_in_the_loop"


class RunStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    AWAITING_RESEARCH_APPROVAL = "awaiting_research_approval"
    AWAITING_DRAFT_APPROVAL = "awaiting_draft_approval"
    COMPLETED = "completed"
    COMPLETED_WITH_WARNINGS = "completed_with_warnings"
    FAILED = "failed"
    CANCELLED = "cancelled"
    EXPIRED = "expired"

    @property
    def is_terminal(self) -> bool:
        return self in TERMINAL_STATUSES

    @property
    def is_awaiting_human(self) -> bool:
        return self in (RunStatus.AWAITING_RESEARCH_APPROVAL, RunStatus.AWAITING_DRAFT_APPROVAL)


TERMINAL_STATUSES = {
    RunStatus.COMPLETED,
    RunStatus.COMPLETED_WITH_WARNINGS,
    RunStatus.FAILED,
    RunStatus.CANCELLED,
    RunStatus.EXPIRED,
}


class Stage(str, Enum):
    PLANNING = "planning"
    RESEARCH = "research"
    SELECTION = "selection"
    SUMMARIZATION = "summarization"
    WRITING = "writing"
    REVIEW = "review"
    REVISION = "revision"
    OUTPUT = "output"


STAGE_ORDER = [s.value for s in Stage]

LogLevel = Literal["info", "running", "success", "warning", "error", "approval"]
StageStatus = Literal["pending", "running", "completed", "skipped", "failed", "waiting"]


# ---------------------------------------------------------------------------
# Goal and plan
# ---------------------------------------------------------------------------

_CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def clean_user_text(value: str | None) -> str | None:
    if value is None:
        return None
    value = _CONTROL_CHARS.sub("", str(value)).strip()
    return re.sub(r"[ \t]+", " ", value) or None


class GoalInput(BaseModel):
    """User request for a newsletter run."""

    model_config = ConfigDict(extra="forbid")

    goal: str = Field(..., max_length=2000)
    mode: ExecutionMode = ExecutionMode.AUTONOMOUS
    topic: str | None = Field(default=None, max_length=120)
    audience: str | None = Field(default=None, max_length=120)
    # None means "not specified": the planner infers from the goal or uses defaults (5 articles, 7 days).
    article_count: int | None = Field(default=None, ge=3, le=7)
    lookback_days: int | None = Field(default=None, ge=1, le=31)
    deterministic: bool = Field(
        default=False, description="Use offline fixture data and rule-based LLM (deterministic test mode)."
    )

    @field_validator("goal", mode="before")
    @classmethod
    def _validate_goal(cls, value: Any) -> str:
        if not isinstance(value, str):
            raise ValueError("Goal must be text.")
        cleaned = clean_user_text(value) or ""
        if not cleaned:
            raise ValueError("Goal must not be empty.")
        if len(cleaned) < 10:
            raise ValueError("Goal is too short. Describe the newsletter you want (at least 10 characters).")
        if len(re.findall(r"[A-Za-z]", cleaned)) < 5:
            raise ValueError("Goal must contain a readable description of the newsletter.")
        return cleaned

    @field_validator("topic", "audience", mode="before")
    @classmethod
    def _clean_optional(cls, value: Any) -> str | None:
        if value is None:
            return None
        if not isinstance(value, str):
            raise ValueError("Must be text.")
        return clean_user_text(value)


class NewsletterConfig(BaseModel):
    topic: str
    audience: str
    article_count: int = Field(ge=3, le=7)
    lookback_days: int = Field(ge=1, le=31)
    cadence: str = "weekly"
    title_hint: str = "AI Agent Weekly"


class PlanTask(BaseModel):
    id: str
    stage: Stage
    title: str
    description: str


class ExecutionPlan(BaseModel):
    normalized_goal: str
    summary: str
    tasks: list[PlanTask]
    research_queries: list[str] = Field(min_length=1, max_length=6)
    output_requirements: list[str]
    assumptions: list[str] = Field(default_factory=list)
    config: NewsletterConfig
    planner: Literal["llm", "heuristic", "heuristic_fallback", "deterministic"] = "heuristic"


# ---------------------------------------------------------------------------
# Research
# ---------------------------------------------------------------------------

DateSource = Literal["search_api", "page_metadata"]
ContentBasis = Literal["full_text", "search_snippet"]
RetrievalStatus = Literal["not_attempted", "retrieved", "failed", "skipped"]


class Article(BaseModel):
    """A normalized candidate article with research and ranking metadata."""

    id: str
    title: str
    url: str
    normalized_url: str
    publisher: str
    domain: str
    snippet: str = ""
    published_date: str | None = None  # ISO date (YYYY-MM-DD) or None when unknown
    date_source: DateSource | None = None
    date_note: str | None = None
    search_query: str | None = None
    search_score: float | None = None
    relevance_score: float = 0.0
    recency_score: float = 0.0
    source_quality: float = 0.5
    final_score: float = 0.0
    rank_reasons: list[str] = Field(default_factory=list)
    content: str | None = None
    content_basis: ContentBasis = "search_snippet"
    retrieval_status: RetrievalStatus = "not_attempted"
    retrieval_note: str | None = None
    duplicates_merged: list[str] = Field(default_factory=list)
    is_test_data: bool = False

    @property
    def source_text(self) -> str:
        """Best available text for summarization (full text or snippet)."""
        if self.content_basis == "full_text" and self.content:
            return self.content
        return self.snippet


# ---------------------------------------------------------------------------
# Writing
# ---------------------------------------------------------------------------


class ArticleSummary(BaseModel):
    article_id: str
    summary: str
    why_it_matters: str
    key_facts: list[str] = Field(default_factory=list)


class NewsletterSection(BaseModel):
    """One story in the newsletter. Source metadata is always copied from the
    researched Article record, never from LLM output."""

    article_id: str
    headline: str
    summary: str
    why_it_matters: str
    key_facts: list[str] = Field(default_factory=list)
    source_url: str
    publisher: str
    published_date: str | None = None
    date_source: DateSource | None = None
    content_basis: ContentBasis = "search_snippet"


class NewsletterDraft(BaseModel):
    subject: str
    preheader: str
    title: str
    intro: str
    sections: list[NewsletterSection]
    closing: str
    generated_at: str
    limitations: list[str] = Field(default_factory=list)
    is_test_data: bool = False
    version: int = 1


# ---------------------------------------------------------------------------
# Review and revision
# ---------------------------------------------------------------------------

Severity = Literal["critical", "major", "minor"]


class ReviewCheck(BaseModel):
    id: str
    label: str
    passed: bool
    score: int = Field(ge=0, le=100)
    weight: int = Field(ge=0)
    details: str


class ReviewIssue(BaseModel):
    id: str
    check_id: str
    severity: Severity
    message: str
    suggestion: str
    article_id: str | None = None
    correctable: bool = True


class ReviewResult(BaseModel):
    attempt: int
    score: int = Field(ge=0, le=100)
    threshold: int
    passed: bool
    revision_required: bool
    checks: list[ReviewCheck]
    issues: list[ReviewIssue]
    summary: str
    reviewer: str = "rules+llm"
    reviewed_at: str = Field(default_factory=utc_now_iso)

    @property
    def critical_issues(self) -> list[ReviewIssue]:
        return [i for i in self.issues if i.severity == "critical"]


class RevisionRecord(BaseModel):
    attempt: int
    trigger: Literal["critic", "user"]
    feedback: str | None = None
    issues_addressed: list[str] = Field(default_factory=list)
    changes: list[str] = Field(default_factory=list)
    score_before: int | None = None
    score_after: int | None = None
    created_at: str = Field(default_factory=utc_now_iso)


# ---------------------------------------------------------------------------
# Observability
# ---------------------------------------------------------------------------


class ToolCallRecord(BaseModel):
    id: str
    tool: str
    stage: str | None = None
    input_summary: str
    status: Literal["running", "success", "error", "fallback"]
    started_at: str
    ended_at: str | None = None
    duration_ms: int | None = None
    result_summary: str | None = None
    error: str | None = None


class LogEntry(BaseModel):
    timestamp: str = Field(default_factory=utc_now_iso)
    stage: str | None = None
    level: LogLevel = "info"
    message: str
    data: dict[str, Any] = Field(default_factory=dict)


class HumanDecision(BaseModel):
    kind: Literal["research", "draft"]
    action: Literal["approve", "revise"]
    selected_ids: list[str] | None = None
    feedback: str | None = None
    decided_at: str = Field(default_factory=utc_now_iso)


class SavedOutput(BaseModel):
    html_path: str
    markdown_path: str
    html_filename: str
    markdown_filename: str
    saved_at: str


class NewsletterResult(BaseModel):
    """Structured result returned by run_newsletter_agent and the result endpoint."""

    run_id: str
    status: RunStatus
    goal: str
    mode: ExecutionMode
    subject: str | None = None
    preheader: str | None = None
    articles: list[NewsletterSection] = Field(default_factory=list)
    review: ReviewResult | None = None
    reviews: list[ReviewResult] = Field(default_factory=list)
    revisions: list[RevisionRecord] = Field(default_factory=list)
    html_path: str | None = None
    markdown_path: str | None = None
    html: str | None = None
    markdown: str | None = None
    delivery_mode: Literal["simulated"] = "simulated"
    delivery_note: str = (
        "Simulated delivery only: the newsletter was saved to disk and was NOT sent to any subscriber."
    )
    warnings: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    plan: ExecutionPlan | None = None
    execution_log: list[LogEntry] = Field(default_factory=list)
    tool_calls: list[ToolCallRecord] = Field(default_factory=list)
    error: str | None = None
    is_test_data: bool = False
    started_at: str | None = None
    finished_at: str | None = None
    duration_seconds: float | None = None
