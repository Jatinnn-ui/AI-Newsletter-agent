"""Node E logic: explicit, structured quality review.

The review combines deterministic rule checks (source integrity, dates,
duplicates, HTML validity, structure, numeric claim support) with an optional
LLM critique (goal alignment, coherence, unsupported claims).

Scoring: weighted average of check scores (0-100). A draft passes only when
score >= threshold AND there are no critical issues, so a high average can
never hide a source-integrity failure.
"""

from __future__ import annotations

import re
from datetime import date

from app.agent.llm_tasks import LLMCritique
from app.models.domain import Article, NewsletterDraft, ReviewCheck, ReviewIssue, ReviewResult
from app.services.ranking import titles_similar
from app.tools.article_retrieval import is_valid_public_url, normalize_url
from app.tools.newsletter_renderer import HtmlValidation

WEIGHTS = {
    "goal_alignment": 15,
    "relevance": 10,
    "source_links": 15,
    "duplicates": 10,
    "coherence": 10,
    "dates": 10,
    "html_valid": 10,
    "article_count": 5,
    "supported_claims": 10,
    "structure": 5,
}
LABELS = {
    "goal_alignment": "Satisfies the user's goal",
    "relevance": "Selected articles are relevant",
    "source_links": "Source URLs present and well-formed",
    "duplicates": "No duplicate stories",
    "coherence": "Summaries are coherent",
    "dates": "Publication dates represented accurately",
    "html_valid": "HTML renders and validates",
    "article_count": "Appropriate article count",
    "supported_claims": "No unsupported factual claims",
    "structure": "Subject, introduction and conclusion present",
}

_NUMBER = re.compile(r"(?<![A-Za-z])\$?\d[\d,]*(?:\.\d+)?%?")
_DELIVERY_CLAIM = re.compile(
    r"\b(has been|was|were|been)\s+(sent|delivered|emailed)\b|\bsubscribers\s+(have\s+)?received\b", re.I
)
_INJECTION = re.compile(r"ignore (all |any )?(previous|prior) instructions|system prompt|api[_ ]?key", re.I)


def _numbers(text: str) -> set[str]:
    return {m.group(0).rstrip(".,").replace(",", "").lstrip("$") for m in _NUMBER.finditer(text or "")}


def unsupported_numbers(claim_text: str, source_text: str) -> list[str]:
    """Numbers that appear in generated text but nowhere in the source."""
    src = _numbers(source_text)
    out = []
    for num in _numbers(claim_text):
        bare = num.rstrip("%")
        if num in src or bare in src or bare in {n.rstrip("%") for n in src}:
            continue
        if len(bare) == 1 and bare in "0123456789":  # small counts like "3 stories" are usually framing
            continue
        out.append(num)
    return sorted(out)


class _Builder:
    def __init__(self) -> None:
        self.issues: list[ReviewIssue] = []
        self.checks: list[ReviewCheck] = []

    def issue(self, check_id: str, severity: str, message: str, suggestion: str, article_id: str | None = None,
              correctable: bool = True) -> None:
        self.issues.append(
            ReviewIssue(
                id=f"{check_id}-{len(self.issues) + 1}",
                check_id=check_id,
                severity=severity,  # type: ignore[arg-type]
                message=message,
                suggestion=suggestion,
                article_id=article_id,
                correctable=correctable,
            )
        )

    def check(self, check_id: str, score: float, details: str) -> None:
        score_i = max(0, min(100, int(round(score))))
        has_blocking = any(i.check_id == check_id and i.severity in ("critical", "major") for i in self.issues)
        self.checks.append(
            ReviewCheck(
                id=check_id,
                label=LABELS[check_id],
                passed=score_i >= 70 and not has_blocking,
                score=score_i,
                weight=WEIGHTS[check_id],
                details=details,
            )
        )


def review_draft(
    *,
    goal: str,
    topic: str,
    requested_count: int,
    draft: NewsletterDraft,
    articles: dict[str, Article],
    validation: HtmlValidation,
    llm: LLMCritique | None,
    attempt: int,
    threshold: int,
    today: date,
    llm_error: str | None = None,
) -> ReviewResult:
    b = _Builder()
    sections = draft.sections
    n = len(sections)

    # 1. Goal alignment ----------------------------------------------------
    if llm is not None:
        goal_score = llm.goal_alignment
        if goal_score < 60:
            b.issue("goal_alignment", "major", f"Reviewer judged goal alignment low ({goal_score}/100).",
                    "Refocus the introduction and summaries on the requested topic and audience.")
        b.check("goal_alignment", goal_score, f"LLM reviewer score {goal_score}/100 against the goal.")
    else:
        topic_terms = {t for t in re.findall(r"[a-z0-9]+", topic.lower()) if len(t) > 2}
        text = (draft.subject + " " + draft.intro).lower()
        hit = sum(1 for t in topic_terms if t in text) / max(len(topic_terms), 1)
        b.check("goal_alignment", 60 + 40 * hit, f"Heuristic: {hit:.0%} of topic terms in subject/intro"
                + (f" (LLM review unavailable: {llm_error})" if llm_error else "") + ".")

    # 2. Relevance ---------------------------------------------------------
    rel_scores = [articles[s.article_id].relevance_score for s in sections if s.article_id in articles]
    rule_rel = (sum(rel_scores) / len(rel_scores) * 100) if rel_scores else 0
    rel = (rule_rel + llm.relevance) / 2 if llm is not None else rule_rel
    for s in sections:
        art = articles.get(s.article_id)
        if art and art.relevance_score < 0.25:
            b.issue("relevance", "minor", f"Story may be weakly related to the topic: {s.headline[:80]}",
                    "Consider replacing it with a more relevant article.", s.article_id, correctable=False)
    b.check("relevance", max(rel, 40 if rel_scores else 0),
            f"Average ranking relevance {rule_rel:.0f}/100" + (f"; LLM relevance {llm.relevance}/100." if llm else "."))

    # 3. Source links (critical) ------------------------------------------
    bad_links = 0
    for s in sections:
        art = articles.get(s.article_id)
        if not is_valid_public_url(s.source_url):
            bad_links += 1
            b.issue("source_links", "critical", f"Missing or malformed source URL for: {s.headline[:80]}",
                    "Restore the original article URL from the research results.", s.article_id)
        elif art is None or normalize_url(s.source_url) != art.normalized_url:
            bad_links += 1
            b.issue("source_links", "critical", f"Source URL does not match a researched article: {s.headline[:80]}",
                    "Use only URLs returned by the research tool.", s.article_id)
    b.check("source_links", 100 if n and not bad_links else (100 * (n - bad_links) / n if n else 0),
            f"{n - bad_links}/{n} stories have a verified source URL.")

    # 4. Duplicates --------------------------------------------------------
    dupes = 0
    seen_urls: dict[str, str] = {}
    for i, s in enumerate(sections):
        key = normalize_url(s.source_url) or s.source_url
        if key in seen_urls:
            dupes += 1
            b.issue("duplicates", "major", f"Duplicate source URL: {s.headline[:80]}",
                    "Remove the repeated story.", s.article_id, correctable=False)
        seen_urls[key] = s.article_id
        for other in sections[:i]:
            if titles_similar(other.headline, s.headline):
                dupes += 1
                b.issue("duplicates", "major", f"Stories appear to cover the same announcement: "
                        f"'{other.headline[:50]}' / '{s.headline[:50]}'",
                        "Keep only one of the overlapping stories.", s.article_id, correctable=False)
                break
    b.check("duplicates", 100 - 35 * dupes, f"{dupes} duplicate story signal(s) found.")

    # 5. Coherence ---------------------------------------------------------
    coherence_penalty = 0
    for s in sections:
        words = len(s.summary.split())
        if words < 12:
            coherence_penalty += 15
            b.issue("coherence", "major", f"Summary is too short ({words} words): {s.headline[:60]}",
                    "Write a 2-3 sentence summary from the source text.", s.article_id)
        elif words > 140:
            coherence_penalty += 10
            b.issue("coherence", "minor", f"Summary is long ({words} words): {s.headline[:60]}",
                    "Trim the summary to under 90 words.", s.article_id)
        if len(s.why_it_matters.split()) < 5:
            coherence_penalty += 10
            b.issue("coherence", "major", f"'Why it matters' is missing or too thin: {s.headline[:60]}",
                    "Add one or two sentences on relevance for the audience.", s.article_id)
    rule_coh = max(0, 100 - coherence_penalty)
    coh = (rule_coh + llm.coherence) / 2 if llm is not None else rule_coh
    b.check("coherence", coh, f"Rule-based coherence {rule_coh}/100" + (f"; LLM {llm.coherence}/100." if llm else "."))

    # 6. Dates (critical when misrepresented) -----------------------------
    date_errors = 0
    unknown = 0
    for s in sections:
        art = articles.get(s.article_id)
        if s.published_date is None:
            unknown += 1
            if art and art.published_date:
                date_errors += 1
                b.issue("dates", "major", f"Verified publication date omitted: {s.headline[:60]}",
                        "Show the publication date from the research record.", s.article_id)
            continue
        try:
            d = date.fromisoformat(s.published_date)
        except ValueError:
            date_errors += 1
            b.issue("dates", "critical", f"Invalid date format: {s.headline[:60]}",
                    "Use the ISO date from the research record.", s.article_id)
            continue
        if d > today:
            date_errors += 1
            b.issue("dates", "critical", f"Publication date is in the future: {s.headline[:60]}",
                    "Mark the date as unavailable.", s.article_id)
        elif art is None or art.published_date != s.published_date:
            date_errors += 1
            b.issue("dates", "critical", f"Date does not match the research record: {s.headline[:60]}",
                    "Copy the date from the research record or mark it unavailable.", s.article_id)
    b.check("dates", 100 - 30 * date_errors,
            f"{date_errors} date error(s); {unknown} stor{'y' if unknown == 1 else 'ies'} labelled 'date unavailable'.")

    # 7. HTML validity (critical) ------------------------------------------
    if not validation.valid:
        b.issue("html_valid", "critical", "HTML validation failed: " + "; ".join(validation.errors[:3]),
                "Re-render the newsletter from the structured draft.")
    b.check("html_valid", 100 if validation.valid else 0,
            "HTML is a complete document with safe links." if validation.valid
            else f"{len(validation.errors)} validation error(s).")

    # 8. Article count ----------------------------------------------------
    count_score = 100
    if n == 0:
        count_score = 0
        b.issue("article_count", "critical", "Newsletter has no stories.", "Research must return at least one article.",
                correctable=False)
    elif n < 3:
        count_score = 50
        b.issue("article_count", "major", f"Only {n} stor{'y' if n == 1 else 'ies'} included (fewer than 3).",
                "Broaden the research window or topic.", correctable=False)
    elif n > 7:
        count_score = 60
        b.issue("article_count", "major", f"{n} stories exceeds the 5-7 target.", "Remove the weakest stories.",
                correctable=False)
    elif n < requested_count:
        stated = any(k in x.lower() for x in draft.limitations for k in ("found", "only", "selected"))
        count_score = 85 if stated else 70
        if not stated:
            b.issue("article_count", "minor", f"{n} stories instead of the requested {requested_count}, "
                    "without an explanation.", "State the limitation in the editorial notes.")
    b.check("article_count", count_score, f"{n} stories (requested {requested_count}).")

    # 9. Unsupported claims ------------------------------------------------
    claim_issues = 0
    for s in sections:
        art = articles.get(s.article_id)
        if art is None:
            continue
        source = f"{art.title} {art.snippet} {art.content or ''}"
        nums = unsupported_numbers(" ".join([s.summary, *s.key_facts]), source)
        if nums:
            claim_issues += 1
            b.issue("supported_claims", "major",
                    f"Figures not found in the source ({', '.join(nums[:4])}): {s.headline[:60]}",
                    "Remove or correct figures that do not appear in the source text.", s.article_id)
        if _INJECTION.search(" ".join([s.summary, s.why_it_matters, *s.key_facts])):
            claim_issues += 1
            b.issue("supported_claims", "critical", f"Possible prompt-injection text in output: {s.headline[:60]}",
                    "Rewrite the summary strictly from the factual source content.", s.article_id)
    if llm is not None:
        valid_ids = {s.article_id for s in sections}
        for claim in llm.unsupported_claims[:10]:
            if claim.article_id not in valid_ids:
                continue
            claim_issues += 1
            b.issue("supported_claims", "major", f"Unsupported claim: \"{claim.claim[:120]}\" ({claim.reason[:120]})",
                    "Remove the claim or rephrase it to match the source.", claim.article_id)
    b.check("supported_claims", 100 - 25 * claim_issues, f"{claim_issues} unsupported claim signal(s).")

    # 10. Structure --------------------------------------------------------
    struct_penalty = 0
    if not draft.subject.strip():
        struct_penalty += 40
        b.issue("structure", "critical", "Subject line is missing.", "Write a specific subject line.")
    elif len(draft.subject) > 90:
        struct_penalty += 15
        b.issue("structure", "minor", f"Subject line is long ({len(draft.subject)} chars).", "Shorten to under 80 characters.")
    if len(draft.intro.split()) < 10:
        struct_penalty += 25
        b.issue("structure", "major", "Introduction is missing or too short.", "Write a 2-4 sentence introduction.")
    if len(draft.closing.split()) < 5:
        struct_penalty += 20
        b.issue("structure", "major", "Closing section is missing or too short.", "Add a concise closing note.")
    if not draft.preheader.strip():
        struct_penalty += 10
        b.issue("structure", "minor", "Preheader is missing.", "Add a one-sentence preheader.")
    framing = " ".join([draft.subject, draft.preheader, draft.intro, draft.closing])
    if _DELIVERY_CLAIM.search(framing):
        struct_penalty += 30
        b.issue("structure", "critical", "Copy claims the newsletter was sent/delivered (delivery is simulated).",
                "Remove any statement that subscribers received the newsletter.")
    b.check("structure", 100 - struct_penalty, "Subject, preheader, introduction and closing checked.")

    if llm is not None:
        for note in llm.notes[:3]:
            b.issue("coherence", "minor", f"Reviewer note: {note[:200]}", note[:200])

    total_weight = sum(c.weight for c in b.checks)
    score = int(round(sum(c.score * c.weight for c in b.checks) / total_weight)) if total_weight else 0
    critical = [i for i in b.issues if i.severity == "critical"]
    major = [i for i in b.issues if i.severity == "major"]
    passed = score >= threshold and not critical
    correctable = [i for i in b.issues if i.correctable and i.severity in ("critical", "major")]
    revision_required = bool(correctable) and (not passed or bool(major))

    if passed and not major:
        summary = f"Passed with {score}/100. {len(b.issues)} minor note(s)."
    elif passed:
        summary = f"Passed with {score}/100, but {len(major)} major issue(s) should be corrected."
    else:
        reason = f"{len(critical)} critical issue(s)" if critical else f"score below threshold {threshold}"
        summary = f"Did not pass ({score}/100): {reason}."

    return ReviewResult(
        attempt=attempt,
        score=score,
        threshold=threshold,
        passed=passed,
        revision_required=revision_required,
        checks=b.checks,
        issues=b.issues,
        summary=summary,
        reviewer="rules+llm" if llm is not None else "rules",
    )
