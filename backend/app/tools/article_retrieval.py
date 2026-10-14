"""Tool 2: Article retrieval and normalization.

* `normalize_search_results` turns raw search results into `Article` records
  (canonical URL, publisher, parsed publication date, stable id).
* `ArticleRetrievalTool` fetches the article page when it is publicly
  accessible, extracts readable paragraph text and publication metadata, and
  falls back to the search snippet when retrieval is not possible. The
  fallback is recorded on the article (`content_basis="search_snippet"`).

Retrieved pages are treated as untrusted data: only plain text is kept, no
markup is ever forwarded to the newsletter.
"""

from __future__ import annotations

import hashlib
import ipaddress
import json
import re
import socket
from datetime import date, datetime, timezone
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser
from typing import Protocol
from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit, urlunsplit

import httpx

from app.models.domain import Article
from app.tools.web_search import SearchResult

# ---------------------------------------------------------------------------
# URL and metadata normalization
# ---------------------------------------------------------------------------

_TRACKING_PARAMS = {
    "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content", "utm_id",
    "gclid", "fbclid", "mc_cid", "mc_eid", "ref", "ref_src", "cmpid", "ocid", "guccounter",
    "taid", "sr_share", "smid", "mod",
}

KNOWN_PUBLISHERS = {
    "techcrunch.com": "TechCrunch",
    "theverge.com": "The Verge",
    "wired.com": "WIRED",
    "venturebeat.com": "VentureBeat",
    "arstechnica.com": "Ars Technica",
    "reuters.com": "Reuters",
    "bloomberg.com": "Bloomberg",
    "cnbc.com": "CNBC",
    "ft.com": "Financial Times",
    "wsj.com": "The Wall Street Journal",
    "nytimes.com": "The New York Times",
    "axios.com": "Axios",
    "technologyreview.com": "MIT Technology Review",
    "zdnet.com": "ZDNET",
    "theinformation.com": "The Information",
    "engadget.com": "Engadget",
    "forbes.com": "Forbes",
    "businessinsider.com": "Business Insider",
    "infoq.com": "InfoQ",
    "siliconangle.com": "SiliconANGLE",
    "theregister.com": "The Register",
    "openai.com": "OpenAI",
    "anthropic.com": "Anthropic",
    "blog.google": "Google",
    "deepmind.google": "Google DeepMind",
    "microsoft.com": "Microsoft",
    "blogs.microsoft.com": "Microsoft",
    "aws.amazon.com": "AWS",
    "nvidia.com": "NVIDIA",
    "blogs.nvidia.com": "NVIDIA",
    "huggingface.co": "Hugging Face",
    "meta.com": "Meta",
    "ai.meta.com": "Meta AI",
    "apnews.com": "AP News",
    "bbc.com": "BBC",
    "bbc.co.uk": "BBC",
    "theguardian.com": "The Guardian",
    "fortune.com": "Fortune",
    "example.com": "Example Publisher (test data)",
    "example.org": "Example Org (test data)",
    "example.net": "Example Net (test data)",
}


def normalize_url(url: str) -> str | None:
    """Canonical form used for duplicate detection. Returns None for non-http URLs."""
    try:
        parts = urlsplit(url.strip())
    except ValueError:
        return None
    scheme = parts.scheme.lower()
    if scheme not in ("http", "https") or not parts.hostname:
        return None
    host = parts.hostname.lower()
    if host.startswith("www."):
        host = host[4:]
    if host.startswith("m.") and host.count(".") >= 2:
        host = host[2:]
    query = [
        (k, v)
        for k, v in parse_qsl(parts.query, keep_blank_values=False)
        if k.lower() not in _TRACKING_PARAMS and not k.lower().startswith("utm_")
    ]
    path = re.sub(r"/+", "/", parts.path or "/")
    if len(path) > 1:
        path = path.rstrip("/")
    for suffix in ("/amp", ".amp"):
        if path.endswith(suffix):
            path = path[: -len(suffix)] or "/"
    return urlunsplit(("https", host, path, urlencode(sorted(query)), ""))


def is_valid_public_url(url: str | None) -> bool:
    if not url:
        return False
    try:
        parts = urlsplit(url)
    except ValueError:
        return False
    return parts.scheme in ("http", "https") and bool(parts.hostname) and "." in (parts.hostname or "")


def domain_of(url: str) -> str:
    host = (urlsplit(url).hostname or "").lower()
    return host[4:] if host.startswith("www.") else host


def publisher_from_domain(domain: str) -> str:
    if domain in KNOWN_PUBLISHERS:
        return KNOWN_PUBLISHERS[domain]
    parts = domain.split(".")
    for i in range(1, len(parts) - 1):
        parent = ".".join(parts[i:])
        if parent in KNOWN_PUBLISHERS:
            return KNOWN_PUBLISHERS[parent]
    core = parts[-2] if len(parts) >= 2 else domain
    return core.replace("-", " ").title() if core else "Unknown publisher"


def article_id_for(normalized_url: str) -> str:
    return hashlib.sha256(normalized_url.encode("utf-8")).hexdigest()[:12]


def parse_date(value: str | None) -> date | None:
    """Parse the date formats returned by search APIs and page metadata."""
    if not value:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        iso = text.replace("Z", "+00:00")
        return datetime.fromisoformat(iso).date()
    except ValueError:
        pass
    try:
        dt = parsedate_to_datetime(text)
        if dt is not None:
            return dt.date()
    except (TypeError, ValueError, IndexError):
        pass
    match = re.search(r"(\d{4})-(\d{2})-(\d{2})", text)
    if match:
        try:
            return date(int(match.group(1)), int(match.group(2)), int(match.group(3)))
        except ValueError:
            return None
    for fmt in ("%B %d, %Y", "%b %d, %Y", "%d %B %Y", "%d %b %Y"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


def _clean_text(text: str) -> str:
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", text or "")
    text = re.sub(r"<[^>]{0,200}>", " ", text)  # strip stray markup from snippets
    return re.sub(r"\s+", " ", text).strip()


def normalize_search_results(results: list[SearchResult], today: date | None = None) -> tuple[list[Article], list[str]]:
    """Convert raw results to Articles. Returns (articles, notes about skipped items)."""
    today = today or datetime.now(timezone.utc).date()
    articles: list[Article] = []
    notes: list[str] = []
    for result in results:
        normalized = normalize_url(result.url)
        if not normalized:
            notes.append(f"Skipped result with unsupported URL: {result.url[:80]}")
            continue
        domain = domain_of(result.url)
        published = parse_date(result.published_date)
        date_note = None
        date_source = None
        if published and published > today:
            date_note = "Search API reported a future date; treated as unavailable."
            published = None
        elif published:
            date_source = "search_api"
        else:
            date_note = "Publication date not provided by the search API."
        articles.append(
            Article(
                id=article_id_for(normalized),
                title=_clean_text(result.title)[:300] or "Untitled article",
                url=result.url.strip(),
                normalized_url=normalized,
                publisher=publisher_from_domain(domain),
                domain=domain,
                snippet=_clean_text(result.content)[:1500],
                published_date=published.isoformat() if published else None,
                date_source=date_source,
                date_note=date_note,
                search_query=result.query,
                search_score=result.score,
                is_test_data=result.is_test_data,
            )
        )
    return articles, notes


# ---------------------------------------------------------------------------
# Page retrieval
# ---------------------------------------------------------------------------


class RetrievalError(Exception):
    pass


class PageFetcher(Protocol):
    def fetch(self, url: str) -> tuple[str, str]:
        """Return (final_url, html). Raise RetrievalError on failure."""


def _host_is_public(host: str) -> bool:
    """SSRF guard: only allow hosts resolving exclusively to public IPs."""
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror:
        return False
    for info in infos:
        try:
            ip = ipaddress.ip_address(info[4][0])
        except ValueError:
            return False
        if not ip.is_global or ip.is_multicast:
            return False
    return bool(infos)


class HttpPageFetcher:
    USER_AGENT = "NewsletterAgent/1.0 (+article-metadata-retrieval)"

    def __init__(self, timeout: float = 8.0, max_bytes: int = 1_500_000, max_redirects: int = 3) -> None:
        self._timeout = timeout
        self._max_bytes = max_bytes
        self._max_redirects = max_redirects

    def fetch(self, url: str) -> tuple[str, str]:
        current = url
        with httpx.Client(timeout=self._timeout, follow_redirects=False) as client:
            for _ in range(self._max_redirects + 1):
                parts = urlsplit(current)
                if parts.scheme not in ("http", "https") or not parts.hostname:
                    raise RetrievalError("Unsupported URL scheme.")
                if not _host_is_public(parts.hostname):
                    raise RetrievalError("Host is not publicly routable; retrieval blocked.")
                try:
                    with client.stream(
                        "GET",
                        current,
                        headers={"User-Agent": self.USER_AGENT, "Accept": "text/html,application/xhtml+xml"},
                    ) as response:
                        if response.status_code in (301, 302, 303, 307, 308):
                            location = response.headers.get("location")
                            if not location:
                                raise RetrievalError("Redirect without location.")
                            current = urljoin(current, location)
                            continue
                        if response.status_code != 200:
                            raise RetrievalError(f"HTTP {response.status_code}")
                        ctype = response.headers.get("content-type", "")
                        if "html" not in ctype.lower():
                            raise RetrievalError(f"Unsupported content type: {ctype[:60] or 'unknown'}")
                        chunks: list[bytes] = []
                        size = 0
                        for chunk in response.iter_bytes():
                            size += len(chunk)
                            if size > self._max_bytes:
                                break
                            chunks.append(chunk)
                        encoding = response.encoding or "utf-8"
                        return current, b"".join(chunks).decode(encoding, errors="replace")
                except httpx.TimeoutException as exc:
                    raise RetrievalError("Timed out") from exc
                except httpx.HTTPError as exc:
                    raise RetrievalError(type(exc).__name__) from exc
        raise RetrievalError("Too many redirects.")


class _ArticleExtractor(HTMLParser):
    """Extract metadata and paragraph text using only the standard library."""

    _SKIP = {"script", "style", "noscript", "nav", "footer", "header", "aside", "form", "svg", "figure"}
    _DATE_KEYS = {
        "article:published_time", "og:published_time", "datepublished", "date", "pubdate",
        "publishdate", "parsely-pub-date", "sailthru.date", "dc.date", "dc.date.issued",
    }

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.meta: dict[str, str] = {}
        self.paragraphs: list[str] = []
        self.jsonld: list[str] = []
        self.title = ""
        self._skip_depth = 0
        self._in_p = False
        self._in_title = False
        self._in_jsonld = False
        self._buf: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        a = {k.lower(): (v or "") for k, v in attrs}
        if tag == "meta":
            key = (a.get("property") or a.get("name") or a.get("itemprop") or "").lower()
            if key and a.get("content"):
                self.meta.setdefault(key, a["content"].strip())
            return
        if tag == "time" and a.get("datetime"):
            self.meta.setdefault("time_datetime", a["datetime"])
        if tag == "script" and a.get("type", "").lower() == "application/ld+json":
            self._in_jsonld = True
            self._buf = []
            return
        if tag in self._SKIP:
            self._skip_depth += 1
            return
        if tag == "title":
            self._in_title = True
        if tag == "p" and self._skip_depth == 0:
            self._in_p = True
            self._buf = []

    def handle_endtag(self, tag: str) -> None:
        if tag == "script" and self._in_jsonld:
            self._in_jsonld = False
            self.jsonld.append("".join(self._buf))
            self._buf = []
            return
        if tag in self._SKIP and self._skip_depth:
            self._skip_depth -= 1
            return
        if tag == "title":
            self._in_title = False
        if tag == "p" and self._in_p:
            self._in_p = False
            text = _clean_text("".join(self._buf))
            if len(text) >= 40:
                self.paragraphs.append(text)
            self._buf = []

    def handle_data(self, data: str) -> None:
        if self._in_jsonld or (self._in_p and self._skip_depth == 0):
            self._buf.append(data)
        elif self._in_title:
            self.title += data

    def published_date(self) -> date | None:
        for key in self._DATE_KEYS:
            if key in self.meta:
                parsed = parse_date(self.meta[key])
                if parsed:
                    return parsed
        for raw in self.jsonld:
            for match in re.finditer(r'"datePublished"\s*:\s*"([^"]+)"', raw):
                parsed = parse_date(match.group(1))
                if parsed:
                    return parsed
        if "time_datetime" in self.meta:
            return parse_date(self.meta["time_datetime"])
        return None

    def site_name(self) -> str | None:
        name = self.meta.get("og:site_name") or self.meta.get("application-name")
        if not name:
            for raw in self.jsonld:
                try:
                    data = json.loads(raw)
                except ValueError:
                    continue
                items = data if isinstance(data, list) else [data]
                for item in items:
                    if isinstance(item, dict) and isinstance(item.get("publisher"), dict):
                        name = item["publisher"].get("name")
                        if name:
                            break
                if name:
                    break
        return _clean_text(name)[:80] if name else None


def extract_article(html: str) -> dict:
    """Parse HTML and return {'text', 'published_date', 'site_name', 'title', 'description'}."""
    parser = _ArticleExtractor()
    try:
        parser.feed(html)
        parser.close()
    except Exception:  # malformed markup: keep whatever was parsed
        pass
    text = "\n\n".join(parser.paragraphs)
    return {
        "text": text[:8000],
        "published_date": parser.published_date(),
        "site_name": parser.site_name(),
        "title": _clean_text(parser.meta.get("og:title") or parser.title)[:300],
        "description": _clean_text(parser.meta.get("og:description") or parser.meta.get("description") or "")[:600],
    }


MIN_FULL_TEXT_CHARS = 600


class ArticleRetrievalTool:
    name = "article_retrieval"

    def __init__(self, fetcher: PageFetcher) -> None:
        self._fetcher = fetcher

    def retrieve(self, article: Article, today: date | None = None) -> Article:
        """Return an updated copy of the article. Never raises for retrieval failures."""
        today = today or datetime.now(timezone.utc).date()
        updated = article.model_copy(deep=True)
        try:
            _, html = self._fetcher.fetch(article.url)
        except RetrievalError as exc:
            updated.retrieval_status = "failed"
            updated.content_basis = "search_snippet"
            updated.retrieval_note = f"Page retrieval failed ({exc}); summary is based on the search snippet only."
            return updated
        except Exception as exc:  # defensive: unknown fetcher errors
            updated.retrieval_status = "failed"
            updated.content_basis = "search_snippet"
            updated.retrieval_note = f"Page retrieval error ({type(exc).__name__}); using search snippet."
            return updated

        info = extract_article(html)
        page_date = info["published_date"]
        if page_date and page_date <= today:
            if updated.published_date and updated.published_date != page_date.isoformat():
                updated.date_note = (
                    f"Search API date {updated.published_date} differs from page metadata; using page metadata."
                )
            else:
                updated.date_note = None
            updated.published_date = page_date.isoformat()
            updated.date_source = "page_metadata"
        if info["site_name"] and not updated.is_test_data and updated.domain not in KNOWN_PUBLISHERS:
            updated.publisher = info["site_name"]
        if not updated.snippet and info["description"]:
            updated.snippet = info["description"]

        text = info["text"]
        if len(text) >= MIN_FULL_TEXT_CHARS:
            updated.content = text
            updated.content_basis = "full_text"
            updated.retrieval_status = "retrieved"
            updated.retrieval_note = f"Retrieved {len(text)} characters of article text."
        else:
            updated.content = text or None
            updated.content_basis = "search_snippet"
            updated.retrieval_status = "retrieved"
            updated.retrieval_note = (
                "Page retrieved but little readable text was found (paywall or script-rendered page); "
                "summary is based on the search snippet."
            )
        return updated
