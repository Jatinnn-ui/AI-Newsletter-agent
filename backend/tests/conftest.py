"""Shared fixtures. Unit tests never touch the network or need API keys."""

from __future__ import annotations

import time
from datetime import date
from pathlib import Path
from typing import Callable

import pytest

from app.agent.services import AgentServices, build_services
from app.config import Settings
from app.models.domain import Article
from app.services.telemetry import DeadlineReporter
from app.tools.article_retrieval import normalize_search_results
from app.tools.fixtures import fixture_search_results

GOAL = "Create a weekly newsletter on the latest AI agent news and send it to our subscribers."


def pytest_configure(config):
    config.addinivalue_line("markers", "live: requires real GEMINI_API_KEY and TAVILY_API_KEY (opt-in)")


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(
        _env_file=None,
        gemini_api_key=None,
        tavily_api_key=None,
        data_dir=tmp_path / "data",
        output_dir=tmp_path / "output",
        cleanup_interval_seconds=3600,
        max_run_seconds=60,
    )


@pytest.fixture
def make_services(settings: Settings) -> Callable[..., AgentServices]:
    """Deterministic services with optional overrides (llm=, search=, storage=)."""

    def factory(reporter=None, **overrides) -> AgentServices:
        svc = build_services(settings, deterministic=True, reporter=reporter or DeadlineReporter(60))
        for key, value in overrides.items():
            setattr(svc, key, value)
        return svc

    return factory


@pytest.fixture
def fixture_articles() -> list[Article]:
    articles, _ = normalize_search_results(fixture_search_results("AI agents"), today=date.today())
    return articles


def wait_for(fn, predicate, timeout: float = 15.0, interval: float = 0.05):
    deadline = time.monotonic() + timeout
    value = fn()
    while time.monotonic() < deadline:
        value = fn()
        if predicate(value):
            return value
        time.sleep(interval)
    raise AssertionError(f"Timed out waiting; last value: {value!r}"[:500])
