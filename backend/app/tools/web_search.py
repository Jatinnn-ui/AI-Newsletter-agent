"""Tool 1: Web search.

`TavilySearchProvider` calls the real Tavily Search REST API
(https://docs.tavily.com/documentation/api-reference/endpoint/search).
`FixtureSearchProvider` returns clearly-labelled TEST DATA for deterministic
mode and unit tests. Results are never invented: if the API fails, a
`SearchError` is raised and reported.
"""

from __future__ import annotations

import time
from datetime import date
from typing import Any, Protocol

import httpx
from pydantic import BaseModel

from app.services.telemetry import redact

TAVILY_SEARCH_URL = "https://api.tavily.com/search"


class SearchError(Exception):
    """Base class for search failures. `recovery` explains what the user can do."""

    recovery = "Check the search provider configuration and try again."


class SearchAuthError(SearchError):
    recovery = "Set a valid TAVILY_API_KEY in the backend environment, or run in deterministic test mode."


class SearchRateLimitError(SearchError):
    recovery = "The search provider rate limit or quota was reached. Wait and retry, or check your Tavily plan."


class SearchUnavailableError(SearchError):
    recovery = "The search provider could not be reached. Check network connectivity and retry."


class SearchResult(BaseModel):
    """A single raw result as returned by the search provider."""

    title: str
    url: str
    content: str = ""
    score: float | None = None
    published_date: str | None = None  # raw provider string; parsed later
    query: str
    is_test_data: bool = False


class SearchProvider(Protocol):
    name: str

    def search(self, query: str, *, start_date: date, max_results: int) -> list[SearchResult]: ...


def parse_tavily_response(payload: Any, query: str) -> list[SearchResult]:
    """Convert a Tavily JSON payload into SearchResult objects.

    Malformed entries (no URL or title) are skipped rather than guessed.
    """
    if not isinstance(payload, dict):
        raise SearchError("Search provider returned an unexpected payload.")
    raw_results = payload.get("results")
    if raw_results is None:
        raise SearchError("Search provider response did not include a results list.")
    if not isinstance(raw_results, list):
        raise SearchError("Search provider results were not a list.")

    parsed: list[SearchResult] = []
    for item in raw_results:
        if not isinstance(item, dict):
            continue
        url = str(item.get("url") or "").strip()
        title = str(item.get("title") or "").strip()
        if not url or not title:
            continue
        score = item.get("score")
        try:
            score = float(score) if score is not None else None
        except (TypeError, ValueError):
            score = None
        published = item.get("published_date")
        parsed.append(
            SearchResult(
                title=title[:300],
                url=url[:2000],
                content=str(item.get("content") or "")[:4000],
                score=score,
                published_date=str(published).strip() if published else None,
                query=query,
            )
        )
    return parsed


class TavilySearchProvider:
    name = "tavily"

    def __init__(
        self,
        api_key: str,
        *,
        search_depth: str = "basic",
        timeout: float = 20.0,
        max_retries: int = 2,
        client: httpx.Client | None = None,
    ) -> None:
        if not api_key:
            raise SearchAuthError("TAVILY_API_KEY is not configured.")
        self._api_key = api_key
        self._depth = search_depth if search_depth in {"basic", "advanced", "fast"} else "basic"
        self._timeout = timeout
        self._max_retries = max_retries
        self._client = client or httpx.Client(timeout=timeout)

    def search(self, query: str, *, start_date: date, max_results: int) -> list[SearchResult]:
        body = {
            "query": query[:400],
            "topic": "news",
            "search_depth": self._depth,
            "max_results": max(1, min(max_results, 20)),
            "start_date": start_date.isoformat(),
            "include_answer": False,
            "include_raw_content": False,
            "include_images": False,
        }
        headers = {"Authorization": f"Bearer {self._api_key}", "Content-Type": "application/json"}
        last_error: Exception | None = None
        for attempt in range(self._max_retries + 1):
            try:
                response = self._client.post(TAVILY_SEARCH_URL, json=body, headers=headers, timeout=self._timeout)
            except httpx.TimeoutException as exc:
                last_error = SearchUnavailableError(f"Search request timed out after {self._timeout}s.")
                last_error.__cause__ = exc
            except httpx.HTTPError as exc:
                last_error = SearchUnavailableError(f"Search request failed: {type(exc).__name__}.")
                last_error.__cause__ = exc
            else:
                status = response.status_code
                if status == 200:
                    try:
                        payload = response.json()
                    except ValueError as exc:
                        raise SearchError("Search provider returned invalid JSON.") from exc
                    return parse_tavily_response(payload, query)
                if status in (401, 403):
                    raise SearchAuthError("Search provider rejected the API key (HTTP %d)." % status)
                if status in (429, 432, 433):
                    last_error = SearchRateLimitError(f"Search provider rate limit or quota reached (HTTP {status}).")
                    if status != 429:  # plan/usage limits will not recover by retrying
                        raise last_error
                elif status >= 500:
                    last_error = SearchUnavailableError(f"Search provider error (HTTP {status}).")
                else:
                    detail = redact(response.text, 200)
                    raise SearchError(f"Search request was rejected (HTTP {status}): {detail}")
            if attempt < self._max_retries:
                time.sleep(min(2 ** attempt, 4))
        assert last_error is not None
        raise last_error


class FixtureSearchProvider:
    """Offline provider returning labelled TEST DATA (see app/tools/fixtures.py)."""

    name = "fixture"

    def __init__(self, fail: bool = False) -> None:
        self._fail = fail

    def search(self, query: str, *, start_date: date, max_results: int) -> list[SearchResult]:
        from app.tools.fixtures import fixture_search_results

        if self._fail:
            raise SearchUnavailableError("Fixture provider configured to fail (test).")
        return fixture_search_results(query)[:max_results]
