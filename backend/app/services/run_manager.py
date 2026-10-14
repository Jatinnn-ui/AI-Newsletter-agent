"""Run lifecycle management for the API.

* Bounded execution: a fixed-size thread pool runs graph segments and the
  number of queued+running runs is capped (HTTP 429 beyond that).
* Persistence: workflow state lives in the LangGraph SQLite checkpointer, so a
  run paused for human approval survives a backend restart; run metadata and
  the event log live in `RunStore`.
* Human-in-the-Loop: a paused run only continues when an API call supplies a
  decision, which is passed to the graph as `Command(resume=...)`.
* Cleanup: paused runs expire after `approval_ttl_hours`; old runs and their
  checkpoints are deleted after `run_retention_days`.
"""

from __future__ import annotations

import logging
import sqlite3
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from typing import Any, Callable

from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.types import Command

from app.agent.graph import build_graph, initial_state
from app.agent.runner import approval_payload, result_from_state
from app.agent.services import AgentServices, ConfigurationError, build_services
from app.config import Settings
from app.models.domain import STAGE_ORDER, GoalInput, RunStatus, utc_now_iso
from app.services.run_store import RunStore
from app.services.telemetry import RunCancelled, RunTimedOut, redact

log = logging.getLogger("newsletter_agent.runs")

ServicesFactory = Callable[[Settings, bool, Any], AgentServices]

VIEW_KEYS = (
    "plan", "candidates", "proposed_ids", "selected_ids", "draft", "html", "markdown", "review", "reviews",
    "revisions", "warnings", "limitations", "output", "user_revisions", "critic_revisions", "human_decisions",
    "started_at", "finished_at",
)


class RunNotFound(Exception):
    pass


class RunConflict(Exception):
    """The requested action is not valid for the run's current status."""


class CapacityExceeded(Exception):
    pass


def _default_factory(settings: Settings, deterministic: bool, reporter: Any) -> AgentServices:
    return build_services(settings, deterministic=deterministic, reporter=reporter)


class RunManager:
    def __init__(
        self,
        settings: Settings,
        *,
        store: RunStore | None = None,
        checkpoint_path: str | None = None,
        services_factory: ServicesFactory | None = None,
        start_cleanup_thread: bool = True,
    ) -> None:
        self.settings = settings
        settings.data_dir.mkdir(parents=True, exist_ok=True)
        self.store = store or RunStore(settings.data_dir / "runs.sqlite")
        cp_path = checkpoint_path or str(settings.data_dir / "checkpoints.sqlite")
        self._cp_conn = sqlite3.connect(cp_path, check_same_thread=False)
        self.checkpointer = SqliteSaver(self._cp_conn)
        self.checkpointer.setup()
        self._factory = services_factory or _default_factory
        self._executor = ThreadPoolExecutor(max_workers=settings.max_concurrent_runs, thread_name_prefix="agent-run")
        self._lock = threading.RLock()
        self._cancel: dict[str, threading.Event] = {}
        self._deadline: dict[str, float] = {}
        self._live: dict[str, dict[str, Any]] = {}  # in-memory stages/view for runs being executed
        self._stop = threading.Event()
        self._recover_interrupted_runs()
        self._cleanup_thread: threading.Thread | None = None
        if start_cleanup_thread:
            self._cleanup_thread = threading.Thread(target=self._cleanup_loop, name="run-cleanup", daemon=True)
            self._cleanup_thread.start()

    # ------------------------------------------------------------------
    # RunReporter protocol (called from worker threads)
    # ------------------------------------------------------------------
    def emit(self, run_id: str, event_type: str, payload: dict[str, Any]) -> None:
        if event_type == "artifact":
            self._apply_artifact(run_id, payload["name"], payload["value"])
            self.store.add_event(run_id, "artifact", {"name": payload["name"]})
            return
        if event_type == "stage":
            self._apply_stage(run_id, payload["stage"], payload["status"])
        self.store.add_event(run_id, event_type, payload)

    def check_cancelled(self, run_id: str) -> None:
        flag = self._cancel.get(run_id)
        if flag is not None and flag.is_set():
            raise RunCancelled("Run cancelled by user.")
        deadline = self._deadline.get(run_id)
        if deadline is not None and time.monotonic() > deadline:
            raise RunTimedOut(f"Run exceeded the {self.settings.max_run_seconds}s execution limit.")

    def _apply_stage(self, run_id: str, stage: str, status: str) -> None:
        with self._lock:
            live = self._live.setdefault(run_id, {"stages": {}, "view": {}})
            live["stages"][stage] = status
            fields: dict[str, Any] = {"stages": live["stages"]}
            if status in ("running", "waiting"):
                fields["current_stage"] = stage
            self.store.update(run_id, **fields)

    def _apply_artifact(self, run_id: str, name: str, value: Any) -> None:
        with self._lock:
            live = self._live.setdefault(run_id, {"stages": {}, "view": {}})
            view = live["view"]
            if name == "plan":
                view["plan"] = value
            elif name == "candidates":
                view["candidates"] = value["candidates"]
                view["proposed_ids"] = value["proposed_ids"]
            elif name == "draft":
                view.update(draft=value["draft"], html=value["html"], markdown=value["markdown"])
            elif name == "review":
                view["review"] = value
                view["reviews"] = [*view.get("reviews", []), value]
            self.store.update(run_id, view=view)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def start_run(self, goal: GoalInput) -> dict[str, Any]:
        deterministic = goal.deterministic or self.settings.deterministic_mode
        if goal.deterministic and not (self.settings.allow_deterministic_runs or self.settings.deterministic_mode):
            raise ConfigurationError("Deterministic test runs are disabled on this server.")
        if not deterministic and not self.settings.live_mode_available:
            # Raises ConfigurationError with a clear message about missing keys.
            self._factory(self.settings, False, self)
        with self._lock:
            if self.store.count_active() >= self.settings.max_pending_runs:
                raise CapacityExceeded("Too many runs are queued or running. Try again shortly.")
            run_id = uuid.uuid4().hex
            goal_dict = goal.model_dump(mode="json") | {"deterministic": deterministic}
            self.store.create(run_id, mode=goal.mode.value, deterministic=deterministic, goal=goal.goal, request=goal_dict)
            stages = {s: "pending" for s in STAGE_ORDER}
            self._live[run_id] = {"stages": stages, "view": {"started_at": utc_now_iso()}}
            self.store.update(run_id, stages=stages, view=self._live[run_id]["view"])
            self._cancel[run_id] = threading.Event()
        self.store.add_event(run_id, "status", {"status": RunStatus.QUEUED.value})
        self._executor.submit(self._execute, run_id, None)
        return self.store.get(run_id) or {}

    def get_run(self, run_id: str) -> dict[str, Any]:
        row = self.store.get(run_id)
        if row is None:
            raise RunNotFound(run_id)
        return row

    def list_runs(self, limit: int = 20) -> list[dict[str, Any]]:
        return self.store.list(limit)

    def approve_research(self, run_id: str, selected_ids: list[str] | None) -> dict[str, Any]:
        with self._lock:
            row = self._require(run_id, RunStatus.AWAITING_RESEARCH_APPROVAL)
            view = row["view"]
            valid = {c["id"] for c in view.get("candidates", [])}
            ids = list(dict.fromkeys(selected_ids)) if selected_ids is not None else list(view.get("proposed_ids", []))
            unknown = [i for i in ids if i not in valid]
            if unknown:
                raise ValueError(f"Unknown article id(s): {', '.join(unknown[:5])}")
            if not 1 <= len(ids) <= 7:
                raise ValueError("Select between 1 and 7 articles.")
            self._resume(run_id, row, {"action": "approve", "selected_ids": ids})
        return self.get_run(run_id)

    def approve_newsletter(self, run_id: str) -> dict[str, Any]:
        with self._lock:
            row = self._require(run_id, RunStatus.AWAITING_DRAFT_APPROVAL)
            self._resume(run_id, row, {"action": "approve"})
        return self.get_run(run_id)

    def request_revision(self, run_id: str, feedback: str | None) -> dict[str, Any]:
        with self._lock:
            row = self._require(run_id, RunStatus.AWAITING_DRAFT_APPROVAL)
            used = int(row["view"].get("user_revisions") or 0)
            if used >= self.settings.max_user_revisions:
                raise RunConflict(
                    f"The limit of {self.settings.max_user_revisions} user-requested revisions has been reached. "
                    "Approve the draft or cancel the run."
                )
            self._resume(run_id, row, {"action": "revise", "feedback": (feedback or "").strip()[:1000]})
        return self.get_run(run_id)

    def cancel(self, run_id: str) -> dict[str, Any]:
        with self._lock:
            row = self.get_run(run_id)
            status = RunStatus(row["status"])
            if status.is_terminal:
                raise RunConflict(f"Run is already {status.value} and cannot be cancelled.")
            flag = self._cancel.setdefault(run_id, threading.Event())
            flag.set()
            if status != RunStatus.RUNNING:
                # Queued or awaiting a human: no worker is executing, finalize now.
                self._finalize_cancelled(run_id, row)
            else:
                self.store.add_event(run_id, "log", {
                    "timestamp": utc_now_iso(), "stage": row.get("current_stage"), "level": "warning",
                    "message": "Cancellation requested; stopping at the next safe point.", "data": {},
                })
        return self.get_run(run_id)

    def shutdown(self) -> None:
        self._stop.set()
        for flag in list(self._cancel.values()):
            flag.set()
        self._executor.shutdown(wait=True, cancel_futures=True)
        try:
            self._cp_conn.close()
        except Exception:  # pragma: no cover
            pass
        self.store.close()

    # ------------------------------------------------------------------
    # Execution
    # ------------------------------------------------------------------
    def _require(self, run_id: str, status: RunStatus) -> dict[str, Any]:
        row = self.get_run(run_id)
        if row["status"] != status.value:
            raise RunConflict(f"Run is '{row['status']}', expected '{status.value}'.")
        return row

    def _resume(self, run_id: str, row: dict[str, Any], decision: dict[str, Any]) -> None:
        view = dict(row["view"])
        view.pop("approval", None)
        self._live[run_id] = {"stages": dict(row["stages"]), "view": view}
        self._cancel.setdefault(run_id, threading.Event())
        self.store.update(run_id, status=RunStatus.QUEUED.value, view=view, awaiting_since=None)
        self.store.add_event(run_id, "status", {"status": RunStatus.QUEUED.value, "decision": decision.get("action")})
        self._executor.submit(self._execute, run_id, decision)

    def _graph(self, deterministic: bool):
        services = self._factory(self.settings, deterministic, self)
        return build_graph(services, checkpointer=self.checkpointer)

    def _execute(self, run_id: str, decision: dict[str, Any] | None) -> None:
        # Atomic queued→running claim. Cancellation uses the inverse transition while
        # holding the same manager lock, so a cancelled queued run cannot be resurrected.
        with self._lock:
            row = self.store.get(run_id)
            if row is None or row["status"] != RunStatus.QUEUED.value:
                return
            flag = self._cancel.get(run_id)
            if flag is not None and flag.is_set():
                return
            if not self.store.transition_status(run_id, RunStatus.QUEUED.value, RunStatus.RUNNING.value):
                return
        self.store.add_event(run_id, "status", {"status": RunStatus.RUNNING.value})
        self._deadline[run_id] = time.monotonic() + self.settings.max_run_seconds
        cfg = {"configurable": {"thread_id": run_id}, "recursion_limit": 60}
        graph = None
        try:
            graph = self._graph(bool(row["deterministic"]))
            payload: Any = (
                Command(resume=decision)
                if decision is not None
                else initial_state(run_id, row["request"], row["view"].get("started_at") or utc_now_iso())
            )
            graph.invoke(payload, cfg)
            self._after_segment(run_id, graph, cfg)
        except RunCancelled:
            self._finalize_cancelled(run_id, self.store.get(run_id) or row, graph, cfg)
        except RunTimedOut as exc:
            self._finalize_failed(run_id, str(exc), graph, cfg)
        except ConfigurationError as exc:
            self._finalize_failed(run_id, str(exc), graph, cfg)
        except Exception as exc:  # defensive: never leave a run stuck in 'running'
            log.exception("Run %s crashed", run_id)
            self._finalize_failed(run_id, f"Internal error ({type(exc).__name__}): {redact(str(exc), 200)}", graph, cfg)
        finally:
            self._deadline.pop(run_id, None)

    def _state_view(self, values: dict[str, Any]) -> dict[str, Any]:
        return {k: values[k] for k in VIEW_KEYS if k in values}

    def _after_segment(self, run_id: str, graph, cfg) -> None:
        snapshot = graph.get_state(cfg)
        values = snapshot.values
        with self._lock:
            live = self._live.setdefault(run_id, {"stages": {}, "view": {}})
            view = live["view"] | self._state_view(values)
            stages = live["stages"]
            if snapshot.interrupts:
                kind = snapshot.interrupts[0].value.get("kind", "research")
                status = (
                    RunStatus.AWAITING_RESEARCH_APPROVAL if kind == "research" else RunStatus.AWAITING_DRAFT_APPROVAL
                )
                view["approval"] = {"kind": kind, "requested_at": utc_now_iso()}
                stage = "selection" if kind == "research" else "output"
                stages[stage] = "waiting"
                self.store.update(
                    run_id, status=status.value, view=view, stages=stages, current_stage=stage,
                    awaiting_since=utc_now_iso(),
                )
                message = (
                    "Waiting for your approval of the proposed articles."
                    if kind == "research"
                    else "Waiting for your approval of the newsletter draft (approve or request a revision)."
                )
                self.store.add_event(run_id, "stage", {"stage": stage, "status": "waiting", "detail": message})
                self.store.add_event(run_id, "log", {
                    "timestamp": utc_now_iso(), "stage": stage, "level": "approval", "message": message, "data": {},
                })
                self.store.add_event(run_id, "status", {"status": status.value})
                self._live.pop(run_id, None)
                return

            final = values.get("status")
            status = RunStatus(final) if final in {s.value for s in RunStatus} else RunStatus.FAILED
            if status == RunStatus.RUNNING:
                status = RunStatus.FAILED
            result = result_from_state(values, run_id=run_id, status=status)
            view["finished_at"] = result.finished_at
            self.store.update(
                run_id, status=status.value, view=view, stages=stages, result=result.model_dump(mode="json"),
                error=result.error, current_stage="output" if status != RunStatus.FAILED else None,
            )
            self.store.add_event(run_id, "status", {"status": status.value, "error": result.error})
            self._live.pop(run_id, None)
            self._cancel.pop(run_id, None)

    def _final_values(self, graph, cfg) -> dict[str, Any]:
        if graph is None:
            return {}
        try:
            return graph.get_state(cfg).values
        except Exception:
            return {}

    def _finalize_failed(self, run_id: str, message: str, graph=None, cfg=None) -> None:
        values = self._final_values(graph, cfg)
        row = self.store.get(run_id) or {}
        with self._lock:
            live = self._live.pop(run_id, None) or {"stages": row.get("stages", {}), "view": row.get("view", {})}
            stages = {k: ("failed" if v == "running" else v) for k, v in live["stages"].items()}
            view = live["view"] | self._state_view(values) | {"finished_at": utc_now_iso()}
            if not values.get("goal_input"):
                values = {**values, "goal_input": row.get("request"), "started_at": view.get("started_at")}
            result = result_from_state(values, run_id=run_id, status=RunStatus.FAILED, error=message)
            self.store.update(
                run_id,
                status=RunStatus.FAILED.value,
                error=message,
                stages=stages,
                view=view,
                result=result.model_dump(mode="json"),
                current_stage=None,
                awaiting_since=None,
            )
        self.store.add_event(run_id, "log", {
            "timestamp": utc_now_iso(), "stage": row.get("current_stage"), "level": "error", "message": message, "data": {},
        })
        self.store.add_event(run_id, "status", {"status": RunStatus.FAILED.value, "error": message})
        self._cancel.pop(run_id, None)

    def _finalize_cancelled(self, run_id: str, row: dict[str, Any], graph=None, cfg=None) -> None:
        values = self._final_values(graph, cfg)
        with self._lock:
            live = self._live.pop(run_id, None) or {"stages": row.get("stages", {}), "view": row.get("view", {})}
            stages = {k: ("cancelled" if v in ("running", "waiting") else v) for k, v in live["stages"].items()}
            view = live["view"] | self._state_view(values) | {"finished_at": utc_now_iso()}
            view.pop("approval", None)
            self.store.update(run_id, status=RunStatus.CANCELLED.value, error="Run cancelled by user.", stages=stages,
                              view=view, awaiting_since=None)
        self.store.add_event(run_id, "log", {
            "timestamp": utc_now_iso(), "stage": row.get("current_stage"), "level": "warning",
            "message": "Run cancelled by user. No newsletter was saved.", "data": {},
        })
        self.store.add_event(run_id, "status", {"status": RunStatus.CANCELLED.value})
        self._cancel.pop(run_id, None)

    # ------------------------------------------------------------------
    # Recovery and cleanup
    # ------------------------------------------------------------------
    def _recover_interrupted_runs(self) -> None:
        for row in self.store.find([RunStatus.QUEUED.value, RunStatus.RUNNING.value]):
            self._finalize_failed(
                row["run_id"],
                "The server restarted while this run was executing. Start a new run.",
            )

    def cleanup_once(self) -> dict[str, int]:
        expired = deleted = 0
        cutoff = datetime.now(timezone.utc) - timedelta(hours=self.settings.approval_ttl_hours)
        for row in self.store.find([RunStatus.AWAITING_RESEARCH_APPROVAL.value, RunStatus.AWAITING_DRAFT_APPROVAL.value]):
            since = row.get("awaiting_since") or row["updated_at"]
            if datetime.fromisoformat(since) < cutoff:
                message = "Approval window expired; the run was abandoned."
                with self._lock:
                    view = dict(row["view"])
                    view.pop("approval", None)
                    view["finished_at"] = utc_now_iso()
                    stages = {
                        key: ("cancelled" if value == "waiting" else value)
                        for key, value in row["stages"].items()
                    }
                    values = {
                        **view,
                        "goal_input": row["request"],
                        "started_at": view.get("started_at"),
                        "finished_at": view["finished_at"],
                    }
                    result = result_from_state(
                        values,
                        run_id=row["run_id"],
                        status=RunStatus.EXPIRED,
                        error=message,
                    )
                    self.store.update(
                        row["run_id"],
                        status=RunStatus.EXPIRED.value,
                        error=message,
                        stages=stages,
                        view=view,
                        result=result.model_dump(mode="json"),
                        current_stage=None,
                        awaiting_since=None,
                    )
                self.store.add_event(row["run_id"], "status", {"status": RunStatus.EXPIRED.value})
                self._delete_checkpoint(row["run_id"])
                expired += 1
        for run_id in self.store.older_than(self.settings.run_retention_days):
            row = self.store.get(run_id)
            if row and RunStatus(row["status"]).is_terminal:
                if not self._delete_artifacts(row):
                    # Keep metadata/checkpoint so the next cleanup cycle can retry.
                    continue
                self.store.delete(run_id)
                self._delete_checkpoint(run_id)
                deleted += 1
        return {"expired": expired, "deleted": deleted}

    def _delete_artifacts(self, row: dict[str, Any]) -> bool:
        """Delete recorded artifacts safely; return False so cleanup can retry on failure."""
        from app.storage.local import LocalFileStorage
        from app.storage.base import StorageError

        output = (row.get("view") or {}).get("output") or (row.get("result") or {})
        storage = LocalFileStorage(self.settings.output_dir)
        succeeded = True
        for key in ("html_path", "markdown_path"):
            path = output.get(key)
            if not path:
                continue
            try:
                storage.delete(path)
            except StorageError as exc:
                succeeded = False
                log.warning("Could not delete %s artifact for run %s; cleanup will retry: %s", key, row["run_id"], exc)
        return succeeded

    def _delete_checkpoint(self, run_id: str) -> None:
        try:
            self.checkpointer.delete_thread(run_id)
        except Exception:  # pragma: no cover - best effort
            log.warning("Could not delete checkpoint for %s", run_id)

    def _cleanup_loop(self) -> None:
        while not self._stop.wait(self.settings.cleanup_interval_seconds):
            try:
                self.cleanup_once()
            except Exception:  # pragma: no cover
                log.exception("Run cleanup failed")
