"""HTTP routes for the Newsletter Agent API."""

from __future__ import annotations

import asyncio
import json
import re
import time
from datetime import datetime, timezone
from typing import Any, AsyncIterator

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import Response, StreamingResponse
from starlette.concurrency import run_in_threadpool

from app import __version__
from app.agent.services import ConfigurationError
from app.api.auth import require_auth
from app.api.schemas import (
    ApprovalInfo,
    ApproveResearchRequest,
    HealthResponse,
    ReviseRequest,
    RunDetail,
    RunMetrics,
    RunSummary,
    StartRunRequest,
)
from app.models.domain import GoalInput, NewsletterResult, RunStatus, utc_now_iso
from app.services.run_manager import CapacityExceeded, RunConflict, RunManager, RunNotFound
from app.storage.base import StorageError
from app.storage.local import LocalFileStorage

router = APIRouter(prefix="/api")  # public: health only
protected = APIRouter(prefix="/api", dependencies=[Depends(require_auth)])
_RUN_ID = re.compile(r"^[a-f0-9]{32}$")


def get_manager(request: Request) -> RunManager:
    return request.app.state.manager


def _valid_run_id(run_id: str) -> str:
    if not _RUN_ID.match(run_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Run not found.")
    return run_id


def _load(manager: RunManager, run_id: str) -> dict[str, Any]:
    try:
        return manager.get_run(_valid_run_id(run_id))
    except RunNotFound:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Run not found.") from None


def _duration(view: dict[str, Any]) -> float | None:
    start = view.get("started_at")
    if not start:
        return None
    end = view.get("finished_at")
    try:
        t0 = datetime.fromisoformat(start)
        t1 = datetime.fromisoformat(end) if end else datetime.now(timezone.utc)
        return round((t1 - t0).total_seconds(), 1)
    except ValueError:
        return None


def build_detail(manager: RunManager, row: dict[str, Any]) -> RunDetail:
    view = row["view"]
    events = manager.store.events(row["run_id"], types=("log", "tool_call"))
    logs = [e["data"] for e in events if e["type"] == "log"]
    calls: dict[str, dict] = {}
    for e in events:
        if e["type"] == "tool_call":
            calls[e["data"]["id"]] = e["data"]
    last_id = manager.store.last_seq(row["run_id"])
    approval = None
    if view.get("approval") and RunStatus(row["status"]).is_awaiting_human:
        approval = ApprovalInfo(
            kind=view["approval"]["kind"],
            requested_at=view["approval"]["requested_at"],
            user_revisions_used=int(view.get("user_revisions") or 0),
            user_revisions_max=manager.settings.max_user_revisions,
        )
    draft = view.get("draft")
    review = view.get("review")
    metrics = RunMetrics(
        duration_seconds=_duration(view),
        article_count=len(draft["sections"]) if draft else len(view.get("selected_ids") or view.get("proposed_ids") or []),
        candidate_count=len(view.get("candidates") or []),
        tool_call_count=len(calls),
        review_score=review["score"] if review else None,
        review_passed=review["passed"] if review else None,
        revision_count=len(view.get("revisions") or []),
    )
    return RunDetail(
        run_id=row["run_id"],
        status=row["status"],
        mode=row["mode"],
        deterministic=row["deterministic"],
        goal=row["goal"],
        request=row["request"] or {},
        current_stage=row.get("current_stage"),
        stages=row["stages"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        error=row.get("error"),
        approval=approval,
        plan=view.get("plan"),
        candidates=view.get("candidates") or [],
        proposed_ids=view.get("proposed_ids") or [],
        selected_ids=view.get("selected_ids") or [],
        draft=draft,
        html=view.get("html"),
        markdown=view.get("markdown"),
        review=review,
        reviews=view.get("reviews") or [],
        revisions=view.get("revisions") or [],
        warnings=view.get("warnings") or [],
        limitations=view.get("limitations") or [],
        output=view.get("output"),
        logs=logs,
        tool_calls=list(calls.values()),
        metrics=metrics,
        last_event_id=last_id,
    )


# ---------------------------------------------------------------------------


@router.get("/health", response_model=HealthResponse)
def health(manager: RunManager = Depends(get_manager)) -> HealthResponse:
    return HealthResponse(
        status="ok",
        version=__version__,
        time=utc_now_iso(),
        config=manager.settings.public_summary(),
        runs={"active": manager.store.count_active(), "max_concurrent": manager.settings.max_concurrent_runs},
    )


@protected.get("/agent/runs", response_model=list[RunSummary])
def list_runs(limit: int = Query(20, ge=1, le=100), manager: RunManager = Depends(get_manager)) -> list[RunSummary]:
    return [RunSummary.model_validate(r) for r in manager.list_runs(limit)]


@protected.post("/agent/runs", response_model=RunDetail, status_code=status.HTTP_202_ACCEPTED)
def start_run(body: StartRunRequest, manager: RunManager = Depends(get_manager)) -> RunDetail:
    try:
        row = manager.start_run(GoalInput.model_validate(body.model_dump()))
    except ConfigurationError as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(exc)) from None
    except CapacityExceeded as exc:
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, str(exc)) from None
    return build_detail(manager, row)


@protected.get("/agent/runs/{run_id}", response_model=RunDetail)
def get_run(run_id: str, manager: RunManager = Depends(get_manager)) -> RunDetail:
    return build_detail(manager, _load(manager, run_id))


@protected.get("/agent/runs/{run_id}/result", response_model=NewsletterResult)
def get_result(run_id: str, manager: RunManager = Depends(get_manager)) -> NewsletterResult:
    row = _load(manager, run_id)
    if not row.get("result"):
        raise HTTPException(status.HTTP_409_CONFLICT, f"Result not available yet (run status: {row['status']}).")
    return NewsletterResult.model_validate(row["result"])


def _action(fn, *args) -> Any:
    try:
        return fn(*args)
    except RunNotFound:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Run not found.") from None
    except RunConflict as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from None
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from None


@protected.post("/agent/runs/{run_id}/approve-research", response_model=RunDetail)
def approve_research(run_id: str, body: ApproveResearchRequest, manager: RunManager = Depends(get_manager)) -> RunDetail:
    row = _action(manager.approve_research, _valid_run_id(run_id), body.selected_ids)
    return build_detail(manager, row)


@protected.post("/agent/runs/{run_id}/approve-newsletter", response_model=RunDetail)
def approve_newsletter(run_id: str, manager: RunManager = Depends(get_manager)) -> RunDetail:
    return build_detail(manager, _action(manager.approve_newsletter, _valid_run_id(run_id)))


@protected.post("/agent/runs/{run_id}/revise", response_model=RunDetail)
def revise(run_id: str, body: ReviseRequest, manager: RunManager = Depends(get_manager)) -> RunDetail:
    return build_detail(manager, _action(manager.request_revision, _valid_run_id(run_id), body.feedback))


@protected.post("/agent/runs/{run_id}/cancel", response_model=RunDetail)
def cancel(run_id: str, manager: RunManager = Depends(get_manager)) -> RunDetail:
    return build_detail(manager, _action(manager.cancel, _valid_run_id(run_id)))


# ---------------------------------------------------------------------------
# Server-Sent Events
# ---------------------------------------------------------------------------

SSE_POLL_SECONDS = 0.4
SSE_HEARTBEAT_SECONDS = 15
SSE_MAX_SECONDS = 1800


def _sse(seq: int | None, event: str, data: Any) -> str:
    head = f"id: {seq}\n" if seq is not None else ""
    return f"{head}event: {event}\ndata: {json.dumps(data, default=str)}\n\n"


@protected.get("/agent/runs/{run_id}/events")
async def events(
    run_id: str,
    request: Request,
    after: int = Query(0, ge=0),
    manager: RunManager = Depends(get_manager),
) -> StreamingResponse:
    _load(manager, run_id)
    last_header = request.headers.get("last-event-id")
    cursor = int(last_header) if last_header and last_header.isdigit() else after

    async def stream() -> AsyncIterator[str]:
        nonlocal cursor
        started = time.monotonic()
        last_beat = started
        yield "retry: 3000\n\n"
        while time.monotonic() - started < SSE_MAX_SECONDS:
            if await request.is_disconnected():
                return
            batch = await run_in_threadpool(manager.store.events, run_id, cursor, None, 500)
            for e in batch:
                cursor = e["seq"]
                yield _sse(e["seq"], e["type"], e["data"])
            if not batch:
                row = await run_in_threadpool(manager.store.get, run_id)
                if row is None:
                    return
                st = RunStatus(row["status"])
                if st.is_terminal:
                    yield _sse(None, "end", {"status": st.value})
                    return
                if time.monotonic() - last_beat > SSE_HEARTBEAT_SECONDS:
                    last_beat = time.monotonic()
                    yield ": heartbeat\n\n"
                await asyncio.sleep(SSE_POLL_SECONDS)
        yield _sse(None, "end", {"status": "stream_timeout"})

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no", "Connection": "keep-alive"},
    )


# ---------------------------------------------------------------------------
# Output files (only the files saved for this run)
# ---------------------------------------------------------------------------

_HTML_CSP = "default-src 'none'; style-src 'unsafe-inline'; img-src data:; base-uri 'none'; form-action 'none'; sandbox"


def _serve(manager: RunManager, run_id: str, kind: str, download: bool) -> Response:
    row = _load(manager, run_id)
    output = (row.get("view") or {}).get("output") or (row.get("result") or {})
    path = output.get("html_path" if kind == "html" else "markdown_path")
    if not path:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No saved newsletter for this run yet.")
    storage = LocalFileStorage(manager.settings.output_dir)
    try:
        resolved = storage.resolve(path)
    except StorageError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Newsletter file not found.") from None
    content = resolved.read_text(encoding="utf-8")
    media = "text/html; charset=utf-8" if kind == "html" else "text/markdown; charset=utf-8"
    headers = {"X-Content-Type-Options": "nosniff", "Cache-Control": "no-store"}
    if kind == "html":
        headers["Content-Security-Policy"] = _HTML_CSP
    if download:
        headers["Content-Disposition"] = f'attachment; filename="{resolved.name}"'
    return Response(content=content, media_type=media, headers=headers)


@protected.get("/agent/runs/{run_id}/newsletter.html")
def newsletter_html(run_id: str, download: bool = False, manager: RunManager = Depends(get_manager)) -> Response:
    return _serve(manager, run_id, "html", download)


@protected.get("/agent/runs/{run_id}/newsletter.md")
def newsletter_md(run_id: str, download: bool = False, manager: RunManager = Depends(get_manager)) -> Response:
    return _serve(manager, run_id, "md", download)
