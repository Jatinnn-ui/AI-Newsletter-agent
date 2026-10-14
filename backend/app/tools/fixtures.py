"""Deterministic TEST DATA for offline runs and unit tests.

Everything in this module is fictional fixture data. Titles are prefixed with
"[TEST DATA]", URLs use the reserved example.* domains (RFC 2606), and the
newsletter produced from it is labelled as test output. It must never be
presented as real-world news.

Publication dates are expressed relative to "today" so the lookback filter
can be exercised deterministically.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from app.tools.article_retrieval import RetrievalError
from app.tools.web_search import SearchResult

# (slug, title, snippet, days_ago or None, score, domain)
_FIXTURES: list[tuple[str, str, str, int | None, float, str]] = [
    (
        "agent-framework-release",
        "Open-source agent framework adds durable workflow checkpoints",
        "A fictional open-source project released version 2.0 of its agent framework with durable "
        "checkpoints, letting long-running agents pause for human approval and resume later.",
        1, 0.93, "example.com",
    ),
    (
        "enterprise-agent-survey",
        "Survey: enterprises move AI agent pilots into production",
        "A fictional industry survey of 400 companies reports that a growing share of AI agent pilots "
        "are moving into production, with evaluation and governance cited as the main blockers.",
        2, 0.9, "example.org",
    ),
    (
        "agent-security-guidance",
        "New guidance targets prompt injection risks in AI agents",
        "A fictional security working group published guidance on prompt injection, recommending that "
        "agents treat retrieved web content as untrusted data and restrict tool permissions.",
        3, 0.88, "example.net",
    ),
    (
        "coding-agent-benchmark",
        "Coding agents benchmark shows gains on multi-file tasks",
        "A fictional benchmark update finds coding agents completing more multi-file software tasks, "
        "while noting that results vary widely with the test harness used.",
        4, 0.86, "example.com",
    ),
    (
        "agent-interop-protocol",
        "Vendors back shared protocol for AI agent tool interoperability",
        "Several fictional vendors announced support for a shared protocol so AI agents can discover "
        "and call external tools in a consistent way.",
        None, 0.84, "example.org",
    ),
    (
        "customer-support-agents",
        "Retailer reports results from AI agent customer support rollout",
        "A fictional retailer says its AI agent now resolves routine customer support requests, with "
        "human staff handling escalations and refunds.",
        5, 0.8, "example.net",
    ),
    (
        "agent-observability-tools",
        "Startups focus on observability tooling for AI agents",
        "Fictional startups are building tracing and evaluation tools that record each AI agent step, "
        "tool call and decision for later review.",
        6, 0.78, "example.com",
    ),
    # Duplicate URL (tracking parameters) of the first fixture.
    (
        "agent-framework-release?utm_source=newsletter&utm_medium=email",
        "Open-source agent framework adds durable workflow checkpoints",
        "Duplicate listing of the framework release with tracking parameters.",
        1, 0.7, "example.com",
    ),
    # Same story, different URL: should be filtered as a duplicate story.
    (
        "framework-checkpoints-recap",
        "Open source agent framework adds durable checkpoints for workflows",
        "Recap of the fictional framework release that adds durable checkpoints for agents.",
        1, 0.69, "example.org",
    ),
    # Outside the default 7-day lookback window.
    (
        "old-agent-news",
        "Earlier AI agent announcement from last quarter",
        "A fictional older AI agent announcement that falls outside the requested time window.",
        60, 0.75, "example.net",
    ),
    # Irrelevant to the topic.
    (
        "gardening-tips",
        "Ten tips for a greener autumn garden",
        "Fictional gardening advice about mulching, bulbs and composting leaves.",
        2, 0.3, "example.com",
    ),
]

# Slugs whose page "retrieval" fails, to exercise the snippet fallback.
_RETRIEVAL_FAILS = {"agent-interop-protocol"}


def _url(slug: str, domain: str) -> str:
    return f"https://{domain}/test-data/{slug}"


def fixture_search_results(query: str, today: date | None = None) -> list[SearchResult]:
    today = today or datetime.now(timezone.utc).date()
    results = []
    for slug, title, snippet, days_ago, score, domain in _FIXTURES:
        published = (today - timedelta(days=days_ago)).isoformat() if days_ago is not None else None
        results.append(
            SearchResult(
                title=f"[TEST DATA] {title}",
                url=_url(slug, domain),
                content=snippet,
                score=score,
                published_date=published,
                query=query,
                is_test_data=True,
            )
        )
    # Rotate deterministically per query so different queries surface results in a different order.
    offset = sum(ord(c) for c in query) % len(results)
    return results[offset:] + results[:offset]


def _fixture_page(title: str, snippet: str, published: str | None) -> str:
    meta = f'<meta property="article:published_time" content="{published}T09:00:00Z">' if published else ""
    body = " ".join(
        [
            snippet,
            "This paragraph is fictional fixture text used to verify the retrieval and summarization "
            "pipeline without network access. It does not describe a real event.",
            "The fixture article explains the change in plain terms, notes that adoption is still early, "
            "and quotes no real people or organisations.",
        ]
    )
    paragraphs = "".join(f"<p>{body}</p>" for _ in range(2))
    return (
        f"<!doctype html><html><head><title>{title}</title>{meta}"
        f'<meta property="og:site_name" content="Fixture Publisher"></head>'
        f"<body><nav>Menu</nav><article>{paragraphs}</article><footer>Footer</footer></body></html>"
    )


class FixturePageFetcher:
    """Offline page fetcher that serves synthetic pages for fixture URLs."""

    def __init__(self, today: date | None = None) -> None:
        self._today = today or datetime.now(timezone.utc).date()

    def fetch(self, url: str) -> tuple[str, str]:
        for slug, title, snippet, days_ago, _score, domain in _FIXTURES:
            if url.split("?")[0] == _url(slug, domain).split("?")[0]:
                if slug in _RETRIEVAL_FAILS:
                    raise RetrievalError("HTTP 403 (fixture simulated paywall)")
                published = (self._today - timedelta(days=days_ago)).isoformat() if days_ago is not None else None
                return url, _fixture_page(title, snippet, published)
        raise RetrievalError("HTTP 404 (not a fixture URL)")
