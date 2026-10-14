"""Dependency container for one agent run.

Live runs use Tavily + HTTP page retrieval + Gemini. Deterministic runs use
labelled fixture data and the rule-based LLM so the workflow can be verified
offline. Tests inject their own fakes.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Callable

from app.agent.llm_tasks import AgentLLM, DeterministicAgentLLM, GeminiAgentLLM
from app.config import Settings
from app.services.llm import GeminiJSONClient, LLMConfigurationError
from app.services.telemetry import RunReporter
from app.storage.base import NewsletterStorage
from app.storage.local import LocalFileStorage
from app.tools.article_retrieval import ArticleRetrievalTool, HttpPageFetcher
from app.tools.fixtures import FixturePageFetcher
from app.tools.web_search import FixtureSearchProvider, SearchAuthError, SearchProvider, TavilySearchProvider


class ConfigurationError(Exception):
    """Live mode was requested but required credentials are missing."""


@dataclass
class AgentServices:
    settings: Settings
    search: SearchProvider
    retrieval: ArticleRetrievalTool
    llm: AgentLLM
    storage: NewsletterStorage
    reporter: RunReporter
    deterministic: bool
    today: Callable[[], date] = lambda: datetime.now(timezone.utc).date()


def build_services(settings: Settings, *, deterministic: bool, reporter: RunReporter) -> AgentServices:
    storage = LocalFileStorage(settings.output_dir)
    if deterministic or settings.deterministic_mode:
        return AgentServices(
            settings=settings,
            search=FixtureSearchProvider(),
            retrieval=ArticleRetrievalTool(FixturePageFetcher()),
            llm=DeterministicAgentLLM(),
            storage=storage,
            reporter=reporter,
            deterministic=True,
        )
    missing = [name for name, ok in (("GEMINI_API_KEY", settings.gemini_configured),
                                     ("TAVILY_API_KEY", settings.tavily_configured)) if not ok]
    if missing:
        raise ConfigurationError(
            f"Live mode requires {', '.join(missing)} in the backend environment. "
            "Add the key(s) to backend/.env and restart, or start a run in deterministic test mode."
        )
    try:
        search = TavilySearchProvider(
            settings.tavily_api_key or "",
            search_depth=settings.tavily_search_depth,
            timeout=settings.search_timeout_seconds,
        )
        client = GeminiJSONClient(
            settings.gemini_api_key,
            settings.gemini_model,
            fallback_models=settings.gemini_fallback_list,
            timeout_seconds=settings.llm_timeout_seconds,
            max_retries=settings.llm_max_retries,
        )
    except (SearchAuthError, LLMConfigurationError) as exc:
        raise ConfigurationError(str(exc)) from exc
    return AgentServices(
        settings=settings,
        search=search,
        retrieval=ArticleRetrievalTool(
            HttpPageFetcher(timeout=settings.retrieval_timeout_seconds, max_bytes=settings.retrieval_max_bytes)
        ),
        llm=GeminiAgentLLM(client),
        storage=storage,
        reporter=reporter,
        deterministic=False,
    )
