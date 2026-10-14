"""3. Research tool parsing  4. Duplicate URLs  5. Duplicate stories  6. Missing dates (+ retrieval fallback)"""

import json
from datetime import date, timedelta

import httpx
import pytest

from app.services.ranking import dedupe_by_url, dedupe_stories, score_articles, select_articles, topic_terms
from app.tools.article_retrieval import (
    ArticleRetrievalTool,
    RetrievalError,
    extract_article,
    normalize_search_results,
    normalize_url,
)
from app.tools.fixtures import FixturePageFetcher
from app.tools.web_search import (
    SearchAuthError,
    SearchError,
    SearchRateLimitError,
    SearchResult,
    TavilySearchProvider,
    parse_tavily_response,
)

TODAY = date(2026, 10, 13)


def _client(handler):
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_parse_tavily_response_skips_malformed_items():
    payload = {"results": [
        {"title": "Agents ship", "url": "https://techcrunch.com/a", "content": "x", "score": "0.9",
         "published_date": "Mon, 12 Oct 2026 10:00:00 GMT"},
        {"title": "", "url": "https://x.com/b"},
        {"url": "https://x.com/c"},
        "garbage",
        {"title": "No score", "url": "https://wired.com/d", "score": "n/a"},
    ]}
    results = parse_tavily_response(payload, "q")
    assert [r.url for r in results] == ["https://techcrunch.com/a", "https://wired.com/d"]
    assert results[0].score == 0.9 and results[1].score is None
    with pytest.raises(SearchError):
        parse_tavily_response({"no": "results"}, "q")


def test_tavily_provider_request_and_errors():
    seen = {}

    def ok(request: httpx.Request):
        seen["auth"] = request.headers["authorization"]
        seen["body"] = request.read().decode()
        return httpx.Response(200, json={"results": [{"title": "T", "url": "https://reuters.com/x", "content": "c"}]})

    provider = TavilySearchProvider("tvly-test-key-123456", client=_client(ok), max_retries=0)
    out = provider.search("AI agents", start_date=TODAY, max_results=5)
    assert out[0].url == "https://reuters.com/x" and out[0].query == "AI agents"
    assert seen["auth"] == "Bearer tvly-test-key-123456"
    body = json.loads(seen["body"])
    assert body["topic"] == "news" and body["start_date"] == TODAY.isoformat() and body["max_results"] == 5

    with pytest.raises(SearchAuthError):
        TavilySearchProvider("k", client=_client(lambda r: httpx.Response(401)), max_retries=0).search(
            "q", start_date=TODAY, max_results=1)
    with pytest.raises(SearchRateLimitError):
        TavilySearchProvider("k", client=_client(lambda r: httpx.Response(429)), max_retries=0).search(
            "q", start_date=TODAY, max_results=1)
    with pytest.raises(SearchAuthError):
        TavilySearchProvider("")


def test_normalize_url_strips_tracking_and_variants():
    a = normalize_url("https://www.Example.com/story/?utm_source=x&id=2&fbclid=abc")
    b = normalize_url("http://example.com/story?id=2")
    assert a == b == "https://example.com/story?id=2"
    assert normalize_url("javascript:alert(1)") is None
    assert normalize_url("ftp://example.com/x") is None


def test_duplicate_urls_removed_keeping_best(fixture_articles):
    unique, removed = dedupe_by_url(fixture_articles)
    assert removed == 1
    assert len({a.normalized_url for a in unique}) == len(unique)
    kept = next(a for a in unique if "agent-framework-release" in a.url)
    assert kept.duplicates_merged and "utm_source" not in kept.url


def test_duplicate_stories_filtered(fixture_articles):
    unique, _ = dedupe_by_url(fixture_articles)
    scored, _ = score_articles(unique, terms=topic_terms("AI agents"), today=date.today(), lookback_days=7)
    kept, removed = dedupe_stories(scored)
    framework = [a for a in kept if "checkpoints" in a.title.lower()]
    assert len(framework) == 1  # recap of the same announcement was dropped
    assert len(removed) == 1


def test_irrelevant_and_old_articles_excluded(fixture_articles):
    unique, _ = dedupe_by_url(fixture_articles)
    scored, notes = score_articles(unique, terms=topic_terms("AI agents"), today=date.today(), lookback_days=7)
    titles = " ".join(a.title for a in scored)
    assert "garden" not in titles and "last quarter" not in titles
    assert any("off-topic" in n for n in notes) and any("window" in n for n in notes)


def test_missing_and_future_publication_dates():
    results = [
        SearchResult(title="AI agents A", url="https://a.com/1", content="ai agent", published_date=None, query="q"),
        SearchResult(title="AI agents B", url="https://b.com/2", content="ai agent",
                     published_date=(TODAY + timedelta(days=3)).isoformat(), query="q"),
        SearchResult(title="AI agents C", url="https://c.com/3", content="ai agent", published_date="2026-10-10", query="q"),
    ]
    arts, _ = normalize_search_results(results, today=TODAY)
    assert arts[0].published_date is None and "not provided" in arts[0].date_note
    assert arts[1].published_date is None and "future" in arts[1].date_note  # never trusted
    assert arts[2].published_date == "2026-10-10" and arts[2].date_source == "search_api"
    scored, _ = score_articles(arts, terms=topic_terms("AI agents"), today=TODAY, lookback_days=7)
    undated = next(a for a in scored if a.url.endswith("/1"))
    assert "publication date unavailable" in undated.rank_reasons


def test_selection_reports_shortfall_instead_of_padding(fixture_articles):
    unique, _ = dedupe_by_url(fixture_articles[:3])
    scored, _ = score_articles(unique, terms=topic_terms("AI agents"), today=date.today(), lookback_days=30)
    selected, notes = select_articles(scored, 7)
    assert len(selected) == len(scored) < 7
    assert notes and "Only" in notes[0]


def test_retrieval_extracts_text_and_date_and_falls_back(fixture_articles):
    tool = ArticleRetrievalTool(FixturePageFetcher())
    ok = next(a for a in fixture_articles if "enterprise-agent-survey" in a.url)
    out = tool.retrieve(ok)
    assert out.content_basis == "full_text" and out.date_source == "page_metadata"
    assert "Menu" not in (out.content or "") and "Footer" not in (out.content or "")

    blocked = next(a for a in fixture_articles if "agent-interop-protocol" in a.url)
    out = tool.retrieve(blocked)
    assert out.retrieval_status == "failed" and out.content_basis == "search_snippet"
    assert "search snippet" in out.retrieval_note

    class Boom:
        def fetch(self, url):
            raise RetrievalError("Timed out")

    assert ArticleRetrievalTool(Boom()).retrieve(ok).content_basis == "search_snippet"


def test_extract_article_reads_jsonld_date_and_ignores_scripts():
    html = ('<html><head><script type="application/ld+json">{"datePublished": "2026-10-01T08:00:00Z",'
            '"publisher": {"name": "Daily Bot"}}</script><script>alert("x")</script></head>'
            '<body><p>' + "Agents are getting better at tool use and planning. " * 3 + '</p></body></html>')
    info = extract_article(html)
    assert info["published_date"] == date(2026, 10, 1)
    assert info["site_name"] == "Daily Bot"
    assert "alert" not in info["text"]
