"""Optional API token authentication (API_AUTH_TOKEN)."""

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.services.run_manager import RunManager
from tests.conftest import GOAL, wait_for

TOKEN = "s3cret-token-for-tests"


@pytest.fixture
def authed(settings):
    settings.api_auth_token = TOKEN
    with TestClient(create_app(settings, RunManager(settings, start_cleanup_thread=False))) as c:
        yield c


def test_health_is_public_and_reports_auth(authed):
    r = authed.get("/api/health")
    assert r.status_code == 200 and r.json()["config"]["auth_required"] is True
    assert TOKEN not in r.text


@pytest.mark.parametrize("headers", [{}, {"Authorization": "Bearer wrong"}, {"X-API-Key": "nope"}])
def test_protected_routes_reject_missing_or_wrong_token(authed, headers):
    assert authed.get("/api/agent/runs", headers=headers).status_code == 401
    r = authed.post("/api/agent/runs", json={"goal": GOAL, "deterministic": True}, headers=headers)
    assert r.status_code == 401 and r.headers["www-authenticate"] == "Bearer"


def test_all_credential_forms_accepted(authed):
    bearer = {"Authorization": f"Bearer {TOKEN}"}
    r = authed.post("/api/agent/runs", json={"goal": GOAL, "deterministic": True}, headers=bearer)
    assert r.status_code == 202
    run_id = r.json()["run_id"]
    wait_for(lambda: authed.get(f"/api/agent/runs/{run_id}", headers=bearer).json(), lambda d: d["status"] == "completed")
    assert authed.get("/api/agent/runs", headers={"X-API-Key": TOKEN}).status_code == 200
    # Streams and downloads use Authorization headers too; credentials never appear in URLs.
    assert authed.get(f"/api/agent/runs/{run_id}/events", headers=bearer).status_code == 200
    assert authed.get(f"/api/agent/runs/{run_id}/newsletter.html", headers=bearer).status_code == 200
    assert authed.get(f"/api/agent/runs/{run_id}/newsletter.html?access_token={TOKEN}").status_code == 401
    assert authed.get(f"/api/agent/runs/{run_id}/newsletter.html").status_code == 401
