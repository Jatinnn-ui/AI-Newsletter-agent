"""Gemini quota handling: daily-quota model switching, per-minute retry, honest failure."""

from types import SimpleNamespace

import pytest
from google.genai import errors

from app.agent.llm_tasks import Editorial
from app.services.llm import EXHAUSTED, GeminiJSONClient, LLMRateLimitError

OK = '{"subject": "s", "preheader": "p", "title": "t", "intro": "i", "closing": "c"}'


def quota_error(per_day: bool, retry: str = "30s") -> errors.ClientError:
    quota_id = "GenerateRequestsPerDayPerProjectPerModel-FreeTier" if per_day else "GenerateRequestsPerMinutePerProjectPerModel-FreeTier"
    return errors.ClientError(429, {"error": {"code": 429, "message": "Quota exceeded", "status": "RESOURCE_EXHAUSTED", "details": [
        {"@type": "type.googleapis.com/google.rpc.QuotaFailure", "violations": [{"quotaId": quota_id, "quotaValue": "20"}]},
        {"@type": "type.googleapis.com/google.rpc.RetryInfo", "retryDelay": retry},
    ]}})


class FakeModels:
    def __init__(self, script: dict[str, list]):
        self.script = script
        self.calls: list[str] = []

    def generate_content(self, *, model, contents, config):
        self.calls.append(model)
        outcome = self.script[model].pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return SimpleNamespace(text=outcome)


@pytest.fixture(autouse=True)
def reset_exhausted():
    EXHAUSTED.clear()
    yield
    EXHAUSTED.clear()


def make(script, sleeps=None):
    models = FakeModels(script)
    client = GeminiJSONClient(None, "main", fallback_models=["backup"], client=SimpleNamespace(models=models),
                              max_retries=2, sleep=(sleeps.append if sleeps is not None else lambda s: None))
    return client, models


def test_daily_quota_switches_to_fallback_and_is_remembered():
    client, models = make({"main": [quota_error(per_day=True, retry="41471s")], "backup": [OK, OK]})
    assert client.generate_json(system="s", prompt="p", schema=Editorial).subject == "s"
    assert client.last_model == "backup"
    # Second call skips the exhausted model entirely (no wasted request).
    client.generate_json(system="s", prompt="p", schema=Editorial)
    assert models.calls == ["main", "backup", "backup"]


def test_per_minute_limit_waits_and_retries_same_model():
    sleeps: list[float] = []
    client, models = make({"main": [quota_error(per_day=False, retry="7s"), OK], "backup": []}, sleeps)
    client.generate_json(system="s", prompt="p", schema=Editorial)
    assert models.calls == ["main", "main"] and sleeps == [7.0]


def test_all_models_exhausted_raises_clear_rate_limit_error():
    client, _ = make({"main": [quota_error(True)], "backup": [quota_error(True)]})
    with pytest.raises(LLMRateLimitError, match="daily free-tier quota"):
        client.generate_json(system="s", prompt="p", schema=Editorial)


def test_overloaded_model_falls_back():
    busy = errors.ServerError(503, {"error": {"code": 503, "message": "high demand", "status": "UNAVAILABLE"}})
    client, models = make({"main": [busy, busy, busy], "backup": [OK]})
    client.generate_json(system="s", prompt="p", schema=Editorial)
    assert models.calls == ["main", "main", "main", "backup"]
