"""Event reporting, tool-call tracking and cooperative cancellation.

Every agent node gets a `NodeContext` which:
  * records log entries and tool calls into the LangGraph state, and
  * forwards them in real time to a `RunReporter` (the run manager streams
    them to the UI via Server-Sent Events).

Messages are passed through `redact()` so API keys never reach logs.
"""

from __future__ import annotations

import re
import time
import uuid
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any, Iterator, Protocol

from app.models.domain import LogEntry, LogLevel, ToolCallRecord, utc_now_iso


class RunCancelled(Exception):
    """Raised inside the workflow when the user cancelled the run."""


class RunTimedOut(Exception):
    """Raised inside the workflow when the run exceeded its time budget."""


_SECRET_PATTERNS = [
    re.compile(r"tvly-[A-Za-z0-9_\-]{6,}"),
    re.compile(r"AIza[0-9A-Za-z_\-]{20,}"),
    re.compile(r"(?i)(bearer\s+)[A-Za-z0-9._\-]{8,}"),
    re.compile(r"(?i)(api[_-]?key[\"'=:\s]+)[A-Za-z0-9._\-]{8,}"),
    re.compile(r"(?i)([?&]key=)[A-Za-z0-9._\-]{8,}"),
]


def redact(text: str | None, max_len: int = 500) -> str:
    """Remove anything that looks like a credential and bound the length."""
    if not text:
        return ""
    out = str(text)
    for pattern in _SECRET_PATTERNS:
        out = pattern.sub(lambda m: (m.group(1) if m.groups() else "") + "[REDACTED]", out)
    if len(out) > max_len:
        out = out[: max_len - 1] + "…"
    return out


class RunReporter(Protocol):
    def emit(self, run_id: str, event_type: str, payload: dict[str, Any]) -> None: ...

    def check_cancelled(self, run_id: str) -> None:
        """Raise RunCancelled / RunTimedOut when the run must stop."""


class DeadlineReporter:
    """Reporter used for direct `run_newsletter_agent` calls: no streaming,
    only an execution time budget (and optional console echo)."""

    def __init__(self, max_seconds: float, echo: bool = False) -> None:
        self._deadline = time.monotonic() + max_seconds
        self._echo = echo

    def emit(self, run_id: str, event_type: str, payload: dict[str, Any]) -> None:
        if self._echo and event_type == "log":
            print(f"[{payload.get('stage') or '-'}] {payload.get('level')}: {payload.get('message')}")

    def check_cancelled(self, run_id: str) -> None:
        if time.monotonic() > self._deadline:
            raise RunTimedOut("The run exceeded its maximum execution time.")


@dataclass
class NodeContext:
    run_id: str
    stage: str
    reporter: RunReporter
    logs: list[dict] = field(default_factory=list)
    tool_calls: list[dict] = field(default_factory=list)

    # -- logging ------------------------------------------------------------
    def log(self, message: str, level: LogLevel = "info", **data: Any) -> None:
        entry = LogEntry(stage=self.stage, level=level, message=redact(message, 800), data=data)
        dumped = entry.model_dump(mode="json")
        self.logs.append(dumped)
        self.reporter.emit(self.run_id, "log", dumped)

    def stage_event(self, status: str, detail: str | None = None, stage: str | None = None) -> None:
        self.reporter.emit(
            self.run_id, "stage", {"stage": stage or self.stage, "status": status, "detail": detail}
        )

    def artifact(self, name: str, value: Any) -> None:
        """Publish an intermediate result (plan, candidates, draft, review) for live UI updates."""
        self.reporter.emit(self.run_id, "artifact", {"name": name, "value": value})

    def check_cancelled(self) -> None:
        self.reporter.check_cancelled(self.run_id)

    # -- tool calls ---------------------------------------------------------
    @contextmanager
    def track(self, tool: str, input_summary: str) -> Iterator["ToolCallHandle"]:
        handle = ToolCallHandle(
            record=ToolCallRecord(
                id=uuid.uuid4().hex[:12],
                tool=tool,
                stage=self.stage,
                input_summary=redact(input_summary, 300),
                status="running",
                started_at=utc_now_iso(),
            )
        )
        started = time.perf_counter()
        self.reporter.emit(self.run_id, "tool_call", handle.record.model_dump(mode="json"))
        try:
            yield handle
        except Exception as exc:  # recorded, then re-raised for the caller
            handle.record.status = "error"
            handle.record.error = redact(f"{type(exc).__name__}: {exc}", 400)
            raise
        finally:
            rec = handle.record
            if rec.status == "running":
                rec.status = "success"
            rec.ended_at = utc_now_iso()
            rec.duration_ms = int((time.perf_counter() - started) * 1000)
            rec.result_summary = redact(rec.result_summary, 300) if rec.result_summary else None
            dumped = rec.model_dump(mode="json")
            self.tool_calls.append(dumped)
            self.reporter.emit(self.run_id, "tool_call", dumped)

    def flush(self) -> dict[str, list[dict]]:
        out = {"execution_log": self.logs, "tool_calls": self.tool_calls}
        self.logs, self.tool_calls = [], []
        return out


@dataclass
class ToolCallHandle:
    record: ToolCallRecord

    def success(self, summary: str) -> None:
        self.record.status = "success"
        self.record.result_summary = summary

    def fallback(self, summary: str, error: str | None = None) -> None:
        self.record.status = "fallback"
        self.record.result_summary = summary
        if error:
            self.record.error = redact(error, 400)

    def fail(self, error: str, summary: str | None = None) -> None:
        self.record.status = "error"
        self.record.error = redact(error, 400)
        self.record.result_summary = summary
