"""Production lifecycle regressions: queued cancellation, restart recovery and retention cleanup."""

from __future__ import annotations

import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi.testclient import TestClient

from app.agent.services import build_services
from app.main import create_app
from app.models.domain import GoalInput, STAGE_ORDER, utc_now_iso
from app.services.run_manager import RunManager
from app.services.run_store import RunStore
from tests.conftest import GOAL, wait_for


def test_queued_cancel_cannot_be_resurrected(settings):
    settings.max_concurrent_runs = 1
    settings.max_pending_runs = 4
    started = threading.Event()
    release = threading.Event()

    def factory(s, deterministic, reporter):
        svc = build_services(s, deterministic=True, reporter=reporter)
        original = svc.search.search

        def blocked(*args, **kwargs):
            started.set()
            release.wait(10)
            return original(*args, **kwargs)

        svc.search.search = blocked
        return svc

    manager = RunManager(settings, services_factory=factory, start_cleanup_thread=False)
    with TestClient(create_app(settings, manager)) as client:
        first = client.post("/api/agent/runs", json={"goal": GOAL, "deterministic": True}).json()["run_id"]
        assert started.wait(5)
        second = client.post("/api/agent/runs", json={"goal": GOAL, "deterministic": True}).json()["run_id"]
        assert client.get(f"/api/agent/runs/{second}").json()["status"] == "queued"
        cancelled = client.post(f"/api/agent/runs/{second}/cancel").json()
        assert cancelled["status"] == "cancelled"
        release.set()
        wait_for(lambda: client.get(f"/api/agent/runs/{first}").json(), lambda d: d["status"] == "completed")
        final = client.get(f"/api/agent/runs/{second}").json()
        assert final["status"] == "cancelled" and final["output"] is None


def test_restart_recovery_creates_terminal_result(settings):
    store = RunStore(settings.data_dir / "restart-runs.sqlite")
    run_id = "a" * 32
    request = GoalInput(goal=GOAL, deterministic=True).model_dump(mode="json")
    store.create(run_id, mode="autonomous", deterministic=True, goal=GOAL, request=request)
    stages = {s: "pending" for s in STAGE_ORDER}
    stages["planning"] = "running"
    store.update(run_id, status="running", stages=stages, current_stage="planning", view={"started_at": utc_now_iso()})

    manager = RunManager(
        settings,
        store=store,
        checkpoint_path=str(settings.data_dir / "restart-checkpoints.sqlite"),
        start_cleanup_thread=False,
    )
    try:
        row = manager.get_run(run_id)
        assert row["status"] == "failed"
        assert row["result"]["status"] == "failed"
        assert row["result"]["finished_at"]
        assert row["current_stage"] is None
    finally:
        manager.shutdown()


def test_retention_cleanup_deletes_run_artifacts(settings):
    manager = RunManager(settings, start_cleanup_thread=False)
    with TestClient(create_app(settings, manager)) as client:
        run_id = client.post("/api/agent/runs", json={"goal": GOAL, "deterministic": True}).json()["run_id"]
        detail = wait_for(
            lambda: client.get(f"/api/agent/runs/{run_id}").json(),
            lambda d: d["status"] == "completed",
        )
        html = Path(detail["output"]["html_path"])
        markdown = Path(detail["output"]["markdown_path"])
        assert html.exists() and markdown.exists()
        old = (datetime.now(timezone.utc) - timedelta(days=10)).isoformat(timespec="milliseconds")
        manager.store._conn.execute("UPDATE runs SET updated_at = ? WHERE run_id = ?", (old, run_id))
        settings.run_retention_days = 1
        assert manager.cleanup_once()["deleted"] == 1
        assert manager.store.get(run_id) is None
        assert not html.exists() and not markdown.exists()


def test_retention_keeps_metadata_when_artifact_delete_fails(settings, monkeypatch):
    """A transient filesystem error must leave the run available for a later cleanup retry."""
    from app.storage.base import StorageError
    from app.storage.local import LocalFileStorage

    manager = RunManager(settings, start_cleanup_thread=False)
    with TestClient(create_app(settings, manager)) as client:
        run_id = client.post("/api/agent/runs", json={"goal": GOAL, "deterministic": True}).json()["run_id"]
        detail = wait_for(
            lambda: client.get(f"/api/agent/runs/{run_id}").json(),
            lambda d: d["status"] == "completed",
        )
        html = Path(detail["output"]["html_path"])
        old = (datetime.now(timezone.utc) - timedelta(days=10)).isoformat(timespec="milliseconds")
        manager.store._conn.execute("UPDATE runs SET updated_at = ? WHERE run_id = ?", (old, run_id))
        settings.run_retention_days = 1

        monkeypatch.setattr(LocalFileStorage, "delete", lambda self, path: (_ for _ in ()).throw(StorageError("busy")))
        assert manager.cleanup_once()["deleted"] == 0
        assert manager.store.get(run_id) is not None
        assert html.exists()
