"""Deduplication, scoring and selection of candidate articles.

All logic here is deterministic and explainable: every score component is
recorded in `Article.rank_reasons` so the UI can show why a story ranked.
"""

from __future__ import annotations

import re
from collections import Counter
from datetime import date
from difflib import SequenceMatcher

from app.models.domain import Article

STOPWORDS = {
    "a", "an", "the", "and", "or", "of", "for", "to", "in", "on", "at", "by", "with", "from", "as",
    "is", "are", "was", "were", "be", "its", "it", "this", "that", "new", "news", "latest", "weekly",
    "week", "update", "updates", "how", "why", "what", "says", "say", "about", "into", "over", "test",
    "data", "after", "amid", "vs", "via", "top", "more", "than", "s",
}

HIGH_QUALITY_DOMAINS = {
    "reuters.com", "apnews.com", "bloomberg.com", "ft.com", "wsj.com", "nytimes.com", "technologyreview.com",
    "techcrunch.com", "theverge.com", "wired.com", "arstechnica.com", "axios.com", "theinformation.com",
    "venturebeat.com", "cnbc.com", "bbc.com", "bbc.co.uk", "theguardian.com", "zdnet.com", "infoq.com",
    "theregister.com", "fortune.com", "engadget.com", "siliconangle.com",
}
OFFICIAL_SOURCE_DOMAINS = {
    "openai.com", "anthropic.com", "blog.google", "deepmind.google", "microsoft.com", "blogs.microsoft.com",
    "aws.amazon.com", "nvidia.com", "blogs.nvidia.com", "huggingface.co", "ai.meta.com", "meta.com",
    "research.google", "ibm.com", "salesforce.com",
}
LOW_QUALITY_DOMAINS = {
    "reddit.com", "youtube.com", "medium.com", "linkedin.com", "x.com", "twitter.com", "facebook.com",
    "quora.com", "pinterest.com", "tiktok.com", "instagram.com",
}

STORY_JACCARD_THRESHOLD = 0.55
STORY_SEQUENCE_THRESHOLD = 0.85
MAX_PER_DOMAIN = 2


def tokenize(text: str) -> list[str]:
    tokens = re.findall(r"[a-z0-9]+", (text or "").lower())
    out = []
    for tok in tokens:
        if tok in STOPWORDS or len(tok) < 2 and tok not in {"ai"}:
            continue
        if len(tok) > 3 and tok.endswith("s") and not tok.endswith("ss"):
            tok = tok[:-1]
        out.append(tok)
    return out


def topic_terms(topic: str, extra: list[str] | None = None) -> list[str]:
    terms = tokenize(topic)
    for query in extra or []:
        terms.extend(tokenize(query))
    counts = Counter(terms)
    # Terms from the topic always count; query-only terms count if repeated.
    topic_set = set(tokenize(topic))
    return sorted(t for t in counts if t in topic_set or counts[t] >= 2)


def _title_key(title: str) -> set[str]:
    cleaned = re.sub(r"^\[test data\]\s*", "", title.lower())
    return set(tokenize(cleaned))


def titles_similar(a: str, b: str) -> bool:
    ta, tb = _title_key(a), _title_key(b)
    if ta and tb:
        jaccard = len(ta & tb) / len(ta | tb)
        if jaccard >= STORY_JACCARD_THRESHOLD:
            return True
    ra = re.sub(r"\W+", " ", a.lower()).strip()
    rb = re.sub(r"\W+", " ", b.lower()).strip()
    return SequenceMatcher(None, ra, rb).ratio() >= STORY_SEQUENCE_THRESHOLD


def dedupe_by_url(articles: list[Article]) -> tuple[list[Article], int]:
    """Remove exact duplicates (same canonical URL). Keeps the best-scored copy."""
    best: dict[str, Article] = {}
    order: list[str] = []
    removed = 0
    for art in articles:
        key = art.normalized_url
        if key not in best:
            best[key] = art
            order.append(key)
            continue
        removed += 1
        keep = best[key]
        if (art.search_score or 0) > (keep.search_score or 0):
            art, keep = keep, art
        if not keep.published_date and art.published_date:
            keep.published_date, keep.date_source, keep.date_note = art.published_date, art.date_source, None
        if len(art.snippet) > len(keep.snippet):
            keep.snippet = art.snippet
        keep.duplicates_merged.append(art.url)
        best[key] = keep
    return [best[k] for k in order], removed


def dedupe_stories(articles: list[Article]) -> tuple[list[Article], list[tuple[str, str]]]:
    """Remove articles that describe the same story (similar titles).

    Articles must already be sorted by preference (best first). Returns the
    kept list and (removed_id, kept_id) pairs.
    """
    kept: list[Article] = []
    removed: list[tuple[str, str]] = []
    for art in articles:
        match = next((k for k in kept if titles_similar(k.title, art.title)), None)
        if match is None:
            kept.append(art)
        else:
            match.duplicates_merged.append(art.url)
            removed.append((art.id, match.id))
    return kept, removed


def source_quality(domain: str, is_test_data: bool = False) -> tuple[float, str]:
    if is_test_data:
        return 0.7, "fixture source (test data)"

    def matches(group: set[str]) -> bool:
        return domain in group or any(domain.endswith("." + d) for d in group)

    if matches(LOW_QUALITY_DOMAINS):
        return 0.25, "user-generated or social platform"
    if matches(OFFICIAL_SOURCE_DOMAINS):
        return 0.9, "official primary source"
    if matches(HIGH_QUALITY_DOMAINS):
        return 1.0, "established news publisher"
    return 0.55, "less-established or unrecognized source"


def score_articles(
    articles: list[Article], *, terms: list[str], today: date, lookback_days: int
) -> tuple[list[Article], list[str]]:
    """Score articles and drop obviously irrelevant or out-of-window items.

    Returns (scored articles sorted best first, notes about exclusions).
    """
    notes: list[str] = []
    scored: list[Article] = []
    term_set = set(terms)
    for art in articles:
        reasons: list[str] = []
        title_tokens = set(tokenize(art.title))
        body_tokens = set(tokenize(art.snippet + " " + (art.content or "")[:2000]))
        if term_set:
            title_cov = len(term_set & title_tokens) / len(term_set)
            body_cov = len(term_set & (title_tokens | body_tokens)) / len(term_set)
            coverage = 0.6 * title_cov + 0.4 * body_cov
        else:
            coverage = 0.5
        if term_set and not (term_set & (title_tokens | body_tokens)):
            notes.append(f"Excluded as off-topic: {art.title[:90]}")
            continue
        relevance = 0.7 * coverage + 0.3 * (art.search_score if art.search_score is not None else 0.5)
        reasons.append(f"topic match {coverage:.0%}")

        if art.published_date:
            age = (today - date.fromisoformat(art.published_date)).days
            if age > lookback_days + 1:
                notes.append(f"Excluded as outside the {lookback_days}-day window ({age} days old): {art.title[:80]}")
                continue
            recency = 0.2 + 0.8 * max(0.0, 1 - age / max(lookback_days, 1))
            reasons.append(f"published {age} day(s) ago")
        else:
            recency = 0.35
            reasons.append("publication date unavailable")

        quality, quality_reason = source_quality(art.domain, art.is_test_data)
        reasons.append(quality_reason)

        art.relevance_score = round(min(relevance, 1.0), 3)
        art.recency_score = round(recency, 3)
        art.source_quality = quality
        art.final_score = round(0.45 * art.relevance_score + 0.25 * recency + 0.30 * quality, 3)
        art.rank_reasons = reasons
        scored.append(art)
    scored.sort(key=lambda a: a.final_score, reverse=True)
    return scored, notes


def select_articles(ranked: list[Article], count: int) -> tuple[list[Article], list[str]]:
    """Pick the top `count` articles, limiting any single domain for diversity."""
    notes: list[str] = []
    selected: list[Article] = []
    per_domain: Counter[str] = Counter()
    for art in ranked:
        if len(selected) >= count:
            break
        if per_domain[art.domain] >= MAX_PER_DOMAIN:
            continue
        selected.append(art)
        per_domain[art.domain] += 1
    if len(selected) < count:
        for art in ranked:
            if len(selected) >= count:
                break
            if all(art.id != s.id for s in selected):
                selected.append(art)  # domain cap relaxed to fill remaining slots
    if len(selected) < count:
        notes.append(
            f"Only {len(selected)} suitable article(s) were found for the requested {count}; "
            "the newsletter includes only verified search results rather than filler stories."
        )
    selected.sort(key=lambda a: a.final_score, reverse=True)
    return selected, notes
