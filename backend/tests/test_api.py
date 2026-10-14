"""18. API validation  19. Status/result endpoints  20. Health without keys  (+ HITL/cancel over HTTP)"""

import threading

import pytest
from fastapi.testclient import TestClient

from app.agent.services import build_services
from app.main import create_app
from app.models.domain import RunStatus
from app.services.run_manager import RunManager
from tests.conftest import GOAL, wait_for

TERMINAL = {s.value for s in RunStatus if s.is_terminal}


@pytest.fixture
def client(settings):
    manager = RunManager(settings, start_cleanup_thread=False)
    with TestClient(create_app(settings, manager)) as c:
        c.manager = manager
        yield c


def _status(client, run_id):
    return client.get(f"/api/agent/runs/{run_id}").json()


def _start(client, **body):
    r = client.post("/api/agent/runs", json={"goal": GOAL, "deterministic": True, **body})
    assert r.status_code == 202, r.text
    return r.json()["run_id"]


def test_health_without_keys_reports_status_without_secrets(client):
    body = client.get("/api/health").json()
    assert body["status"] == "ok"
    cfg = body["config"]
    assert cfg["llm_configured"] is False and cfg["search_configured"] is False and cfg["live_mode_available"] is False
    assert cfg["delivery_mode"] == "simulated"
    assert not any("key" in k and isinstance(v, str) for k, v in cfg.items())


@pytest.mark.parametrize("body", [
    {},
    {"goal": ""},
    {"goal": "hi"},
    {"goal": GOAL, "article_count": 20},
    {"goal": GOAL, "lookback_days": 0},
    {"goal": GOAL, "mode": "yolo"},
    {"goal": GOAL, "extra": 1},
    {"goal": "x" * 3000},
])
def test_start_run_validation(client, body):
    r = client.post("/api/agent/runs", json=body)
    assert r.status_code == 422
    assert r.json()["detail"] == "Invalid request."


def test_live_run_without_keys_is_rejected_clearly(client):
    r = client.post("/api/agent/runs", json={"goal": GOAL})
    assert r.status_code == 503
    assert "GEMINI_API_KEY" in r.json()["detail"] and "TAVILY_API_KEY" in r.json()["detail"]


def test_body_size_limit(client):
    r = client.post("/api/agent/runs", content=b"{" + b" " * 70000 + b"}", headers={"content-type": "application/json"})
    assert r.status_code == 413


def test_unknown_and_malformed_run_ids(client):
    assert client.get("/api/agent/runs/" + "0" * 32).status_code == 404
    assert client.get("/api/agent/runs/../../etc").status_code == 404
    assert client.get("/api/agent/runs/not-a-run/newsletter.html").status_code == 404


def test_autonomous_run_status_result_files_and_events(client):
    run_id = _start(client)
    detail = wait_for(lambda: _status(client, run_id), lambda d: d["status"] in TERMINAL)
    assert detail["status"] == "completed"
    assert all(v in ("completed", "skipped") for v in detail["stages"].values())
    assert detail["stages"]["revision"] == "skipped"
    assert detail["metrics"]["article_count"] >= 5 and detail["metrics"]["review_score"] >= 80
    assert detail["logs"] and detail["tool_calls"]

    result = client.get(f"/api/agent/runs/{run_id}/result").json()
    assert result["status"] == "completed" and result["delivery_mode"] == "simulated"
    assert result["subject"] and result["html_path"] and len(result["articles"]) >= 5

    html = client.get(f"/api/agent/runs/{run_id}/newsletter.html")
    assert html.status_code == 200 and "sandbox" in html.headers["content-security-policy"]
    assert html.text.startswith("<!DOCTYPE html>")
    md = client.get(f"/api/agent/runs/{run_id}/newsletter.md?download=true")
    assert md.status_code == 200 and "attachment" in md.headers["content-disposition"]

    stream = client.get(f"/api/agent/runs/{run_id}/events")
    assert stream.headers["content-type"].startswith("text/event-stream")
    assert "event: log" in stream.text and "event: tool_call" in stream.text and "event: end" in stream.text
    resumed = client.get(f"/api/agent/runs/{run_id}/events", headers={"Last-Event-ID": str(detail["last_event_id"])})
    assert "event: log" not in resumed.text

    runs = client.get("/api/agent/runs").json()
    assert runs[0]["run_id"] == run_id


def test_result_not_ready_returns_409(client):
    run_id = _start(client, mode="human_in_the_loop")
    wait_for(lambda: _status(client, run_id), lambda d: d["status"] == "awaiting_research_approval")
    assert client.get(f"/api/agent/runs/{run_id}/result").status_code == 409
    assert client.get(f"/api/agent/runs/{run_id}/newsletter.html").status_code == 404


def test_hitl_flow_over_http(client):
    run_id = _start(client, mode="human_in_the_loop")
    d = wait_for(lambda: _status(client, run_id), lambda d: d["status"] == "awaiting_research_approval")
    assert d["approval"]["kind"] == "research" and d["stages"]["selection"] == "waiting"
    assert d["draft"] is None  # genuinely paused before writing

    # wrong-stage actions are rejected
    assert client.post(f"/api/agent/runs/{run_id}/approve-newsletter").status_code == 409
    assert client.post(f"/api/agent/runs/{run_id}/approve-research", json={"selected_ids": ["nope"]}).status_code == 422
    assert client.post(f"/api/agent/runs/{run_id}/approve-research", json={"selected_ids": []}).status_code == 422

    keep = d["proposed_ids"][1:]  # user removes one article
    assert client.post(f"/api/agent/runs/{run_id}/approve-research", json={"selected_ids": keep}).status_code == 200
    d = wait_for(lambda: _status(client, run_id), lambda d: d["status"] == "awaiting_draft_approval")
    assert [s["article_id"] for s in d["draft"]["sections"]] == keep
    assert d["html"] and d["output"] is None

    r = client.post(f"/api/agent/runs/{run_id}/revise", json={"feedback": "Shorter please"})
    assert r.status_code == 200
    d = wait_for(lambda: _status(client, run_id), lambda d: d["status"] == "awaiting_draft_approval" and d["revisions"])
    assert d["revisions"][-1]["trigger"] == "user"

    assert client.post(f"/api/agent/runs/{run_id}/approve-newsletter").status_code == 200
    d = wait_for(lambda: _status(client, run_id), lambda d: d["status"] in TERMINAL)
    assert d["status"] in ("completed", "completed_with_warnings") and d["output"]["html_filename"]
    assert client.post(f"/api/agent/runs/{run_id}/cancel").status_code == 409  # terminal


def test_user_revision_limit(client, settings):
    settings.max_user_revisions = 1
    run_id = _start(client, mode="human_in_the_loop")
    wait_for(lambda: _status(client, run_id), lambda d: d["status"] == "awaiting_research_approval")
    client.post(f"/api/agent/runs/{run_id}/approve-research", json={})
    wait_for(lambda: _status(client, run_id), lambda d: d["status"] == "awaiting_draft_approval")
    client.post(f"/api/agent/runs/{run_id}/revise", json={"feedback": "x"})
    wait_for(lambda: _status(client, run_id), lambda d: d["status"] == "awaiting_draft_approval" and d["revisions"])
    r = client.post(f"/api/agent/runs/{run_id}/revise", json={"feedback": "again"})
    assert r.status_code == 409 and "limit" in r.json()["detail"]


def test_cancel_paused_run(client):
    run_id = _start(client, mode="human_in_the_loop")
    wait_for(lambda: _status(client, run_id), lambda d: d["status"] == "awaiting_research_approval")
    r = client.post(f"/api/agent/runs/{run_id}/cancel")
    assert r.status_code == 200 and r.json()["status"] == "cancelled"
    assert client.post(f"/api/agent/runs/{run_id}/approve-research", json={}).status_code == 409
    assert client.get(f"/api/agent/runs/{run_id}/newsletter.html").status_code == 404


def test_cancel_running_run(settings):
    started = threading.Event()
    release = threading.Event()

    def factory(s, deterministic, reporter):
        svc = build_services(s, deterministic=True, reporter=reporter)
        original = svc.search.search

        def slow_search(*a, **k):
            started.set()
            release.wait(5)
            return original(*a, **k)

        svc.search.search = slow_search
        return svc

    manager = RunManager(settings, services_factory=factory, start_cleanup_thread=False)
    with TestClient(create_app(settings, manager)) as c:
        run_id = _start(c)
        assert started.wait(5)
        r = c.post(f"/api/agent/runs/{run_id}/cancel")
        assert r.status_code == 200
        release.set()
        d = wait_for(lambda: _status(c, run_id), lambda d: d["status"] in TERMINAL)
        assert d["status"] == "cancelled" and d["output"] is None


def test_capacity_limit(settings):
    settings.max_pending_runs = 1
    release = threading.Event()

    def factory(s, deterministic, reporter):
        svc = build_services(s, deterministic=True, reporter=reporter)
        original = svc.search.search
        svc.search.search = lambda *a, **k: (release.wait(5), original(*a, **k))[1]
        return svc

    manager = RunManager(settings, services_factory=factory, start_cleanup_thread=False)
    with TestClient(create_app(settings, manager)) as c:
        _start(c)
        r = c.post("/api/agent/runs", json={"goal": GOAL, "deterministic": True})
        assert r.status_code == 429
        release.set()


def test_paused_run_survives_restart_and_expires(settings):
    m1 = RunManager(settings, start_cleanup_thread=False)
    with TestClient(create_app(settings, m1)) as c:
        run_id = _start(c, mode="human_in_the_loop")
        wait_for(lambda: _status(c, run_id), lambda d: d["status"] == "awaiting_research_approval")
    # New manager (simulated restart) resumes from the SQLite checkpoint.
    m2 = RunManager(settings, start_cleanup_thread=False)
    with TestClient(create_app(settings, m2)) as c:
        assert c.post(f"/api/agent/runs/{run_id}/approve-research", json={}).status_code == 200
        wait_for(lambda: _status(c, run_id), lambda d: d["status"] == "awaiting_draft_approval")
        settings.approval_ttl_hours = 0
        assert m2.cleanup_once()["expired"] == 1
        assert _status(c, run_id)["status"] == "expired"


def test_chunked_body_without_content_length_is_capped(client):
    """The ASGI body cap must not rely only on Content-Length."""
    chunks = (part for part in (b'{"goal":"', b"x" * 70_000, b'"}'))
    response = client.post("/api/agent/runs", content=chunks, headers={"content-type": "application/json"})
    assert response.status_code == 413


def test_production_requires_api_auth_token(settings):
    settings.app_env = "production"
    settings.api_auth_token = None
    with pytest.raises(RuntimeError, match="API_AUTH_TOKEN is required"):
        create_app(settings, RunManager(settings, start_cleanup_thread=False))
