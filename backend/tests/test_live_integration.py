"""Live integration test (opt-in). Uses real Tavily + Gemini and costs API credits.

    $env:RUN_LIVE_TESTS="1"; pytest -m live        (PowerShell)
    RUN_LIVE_TESTS=1 pytest -m live                 (bash)
"""

import os

import pytest

from app.agent.runner import RunOptions, run_newsletter_agent
from app.config import get_settings
from app.tools.article_retrieval import is_valid_public_url

pytestmark = pytest.mark.live

settings = get_settings()
skip = not (os.getenv("RUN_LIVE_TESTS") == "1" and settings.live_mode_available)


@pytest.mark.skipif(skip, reason="Set RUN_LIVE_TESTS=1 and configure GEMINI_API_KEY + TAVILY_API_KEY")
def test_live_autonomous_run_uses_real_sources():
    result = run_newsletter_agent(
        "Create a weekly newsletter on the latest AI agent news and send it to our subscribers.",
        RunOptions(echo=True),
    )
    assert result.status.value.startswith("completed"), result.error
    assert not result.is_test_data
    assert result.articles
    for section in result.articles:
        assert is_valid_public_url(section.source_url)
        assert "example." not in section.source_url
    assert any(t.tool.startswith("web_search (tavily)") and t.status == "success" for t in result.tool_calls)
