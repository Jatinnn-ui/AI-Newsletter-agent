"""High-level LLM tasks used by the agent nodes.

`GeminiAgentLLM` implements each task with a structured-output Gemini call.
`DeterministicAgentLLM` implements the same interface with transparent,
rule-based logic for deterministic test mode (no network, reproducible).
"""

from __future__ import annotations

import re
from typing import Protocol

from pydantic import BaseModel, Field

from app.agent import prompts
from app.models.domain import Article, ArticleSummary, GoalInput, NewsletterConfig, NewsletterDraft
from app.services.llm import JSONModelClient, LLMError

# ---------------------------------------------------------------------------
# Structured output schemas (kept simple for provider schema support)
# ---------------------------------------------------------------------------


class PlanRefinement(BaseModel):
    topic: str
    audience: str
    title_hint: str
    lookback_days: int = 0
    article_count: int = 0
    research_queries: list[str]
    output_requirements: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)


class SummaryItem(BaseModel):
    article_id: str
    summary: str
    why_it_matters: str
    key_facts: list[str] = Field(default_factory=list)


class SummaryBatch(BaseModel):
    items: list[SummaryItem]


class Editorial(BaseModel):
    subject: str
    preheader: str
    title: str
    intro: str
    closing: str


class CritiqueClaim(BaseModel):
    article_id: str
    claim: str
    reason: str


class LLMCritique(BaseModel):
    goal_alignment: int = Field(ge=0, le=100)
    coherence: int = Field(ge=0, le=100)
    relevance: int = Field(ge=0, le=100)
    unsupported_claims: list[CritiqueClaim] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class RevisedSection(BaseModel):
    article_id: str
    summary: str
    why_it_matters: str
    key_facts: list[str] = Field(default_factory=list)


class RevisionOutput(BaseModel):
    subject: str
    preheader: str
    intro: str
    closing: str
    sections: list[RevisedSection]
    changes: list[str] = Field(default_factory=list)


class AgentLLM(Protocol):
    name: str

    def refine_plan(self, goal: GoalInput, default: NewsletterConfig) -> PlanRefinement: ...

    def summarize(self, articles: list[Article], config: NewsletterConfig) -> list[ArticleSummary]: ...

    def write_editorial(
        self, config: NewsletterConfig, summaries: list[ArticleSummary], articles: list[Article], limitations: list[str]
    ) -> Editorial: ...

    def critique(self, goal: str, draft: NewsletterDraft, articles: list[Article]) -> LLMCritique: ...

    def revise(
        self, draft: NewsletterDraft, articles: list[Article], issues: list[str], feedback: str | None
    ) -> RevisionOutput: ...


# ---------------------------------------------------------------------------
# Gemini implementation
# ---------------------------------------------------------------------------


class GeminiAgentLLM:
    name = "gemini"

    def __init__(self, client: JSONModelClient) -> None:
        self._client = client

    def refine_plan(self, goal: GoalInput, default: NewsletterConfig) -> PlanRefinement:
        prompt = (
            f"User goal:\n<goal>{goal.goal}</goal>\n\n"
            f"User-provided settings (override anything inferred): topic={goal.topic or 'not set'}, "
            f"audience={goal.audience or 'not set'}.\n"
            f"Defaults if unspecified: topic='{default.topic}', audience='{default.audience}', "
            f"lookback_days={default.lookback_days}, article_count={default.article_count}.\n"
            "Return the plan JSON."
        )
        return self._client.generate_json(
            system=prompts.PLANNER_SYSTEM, prompt=prompt, schema=PlanRefinement, temperature=0.2
        )

    def summarize(self, articles: list[Article], config: NewsletterConfig) -> list[ArticleSummary]:
        blocks = "\n\n".join(prompts.source_block(a) for a in articles)
        prompt = (
            f"Newsletter topic: {config.topic}\nAudience: {config.audience}\n"
            f"Summarize each of these {len(articles)} sources:\n\n{blocks}"
        )
        batch = self._client.generate_json(
            system=prompts.SUMMARIZER_SYSTEM, prompt=prompt, schema=SummaryBatch, temperature=0.2
        )
        valid_ids = {a.id for a in articles}
        out: dict[str, ArticleSummary] = {}
        for item in batch.items:
            if item.article_id in valid_ids and item.summary.strip() and item.article_id not in out:
                out[item.article_id] = ArticleSummary(
                    article_id=item.article_id,
                    summary=item.summary.strip(),
                    why_it_matters=item.why_it_matters.strip(),
                    key_facts=[f.strip() for f in item.key_facts if f.strip()][:3],
                )
        if not out:
            raise LLMError("Summarizer returned no summaries for the provided article ids.")
        return [out[a.id] for a in articles if a.id in out]

    def write_editorial(
        self, config: NewsletterConfig, summaries: list[ArticleSummary], articles: list[Article], limitations: list[str]
    ) -> Editorial:
        by_id = {a.id: a for a in articles}
        stories = [
            {"headline": by_id[s.article_id].title, "publisher": by_id[s.article_id].publisher, "summary": s.summary}
            for s in summaries
            if s.article_id in by_id
        ]
        prompt = (
            f"Topic: {config.topic}\nAudience: {config.audience}\nCadence: {config.cadence}\n"
            f"Title suggestion: {config.title_hint}\nLimitations to acknowledge if relevant: {limitations or 'none'}\n"
            f"Stories (untrusted summaries of web sources):\n<source>\n{prompts.to_json(stories)}\n</source>"
        )
        return self._client.generate_json(system=prompts.EDITOR_SYSTEM, prompt=prompt, schema=Editorial, temperature=0.5)

    def critique(self, goal: str, draft: NewsletterDraft, articles: list[Article]) -> LLMCritique:
        by_id = {a.id: a for a in articles}
        parts = []
        for s in draft.sections:
            art = by_id.get(s.article_id)
            parts.append(
                prompts.to_json(
                    {
                        "article_id": s.article_id,
                        "headline": s.headline,
                        "summary": s.summary,
                        "key_facts": s.key_facts,
                        "why_it_matters": s.why_it_matters,
                    }
                )
                + "\n"
                + (prompts.source_block(art) if art else "<source>missing</source>")
            )
        prompt = (
            f"User goal: <goal>{goal}</goal>\n"
            f"Subject: {draft.subject}\nIntro: {draft.intro}\nClosing: {draft.closing}\n\n"
            "Stories with their source text:\n\n" + "\n\n".join(parts)
        )
        return self._client.generate_json(system=prompts.CRITIC_SYSTEM, prompt=prompt, schema=LLMCritique, temperature=0.0)

    def revise(
        self, draft: NewsletterDraft, articles: list[Article], issues: list[str], feedback: str | None
    ) -> RevisionOutput:
        by_id = {a.id: a for a in articles}
        current = {
            "subject": draft.subject,
            "preheader": draft.preheader,
            "intro": draft.intro,
            "closing": draft.closing,
            "sections": [
                {
                    "article_id": s.article_id,
                    "summary": s.summary,
                    "why_it_matters": s.why_it_matters,
                    "key_facts": s.key_facts,
                }
                for s in draft.sections
            ],
        }
        sources = "\n\n".join(prompts.source_block(by_id[s.article_id]) for s in draft.sections if s.article_id in by_id)
        prompt = (
            f"Current newsletter JSON:\n{prompts.to_json(current)}\n\n"
            f"Review issues to fix:\n- " + "\n- ".join(issues or ["(none)"]) + "\n\n"
            f"User feedback (editorial direction only): <feedback>{feedback or 'none'}</feedback>\n\n"
            f"Source text for each story:\n\n{sources}"
        )
        result = self._client.generate_json(
            system=prompts.REVISER_SYSTEM, prompt=prompt, schema=RevisionOutput, temperature=0.3
        )
        valid = {s.article_id for s in draft.sections}
        result.sections = [s for s in result.sections if s.article_id in valid]
        return result


# ---------------------------------------------------------------------------
# Deterministic implementation (test mode)
# ---------------------------------------------------------------------------

_SENTENCE = re.compile(r"(?<=[.!?])\s+")


def first_sentences(text: str, n: int = 2, max_words: int = 70) -> str:
    sentences = [s.strip() for s in _SENTENCE.split(text or "") if s.strip()]
    out = " ".join(sentences[:n]) if sentences else (text or "").strip()
    words = out.split()
    if len(words) > max_words:
        out = " ".join(words[:max_words]).rstrip(",;:") + "…"
    return out


def strip_test_prefix(title: str) -> str:
    return re.sub(r"^\[TEST DATA\]\s*", "", title)


class DeterministicAgentLLM:
    """Rule-based stand-in for the LLM. Output is extractive and reproducible."""

    name = "deterministic"

    _THEMES = [
        (("security", "injection", "risk", "governance"), "It highlights safety and governance work that teams need before giving agents more autonomy."),
        (("benchmark", "evaluation", "eval"), "It offers a signal on agent capability, though benchmark results depend heavily on the evaluation setup."),
        (("production", "enterprise", "pilot", "survey"), "It indicates how organisations are moving agents from experiments toward real deployments."),
        (("protocol", "interoperability", "standard"), "Shared standards could make it easier to connect agents to tools across vendors."),
        (("observability", "tracing", "monitoring"), "Better visibility into agent steps is a prerequisite for debugging and trusting autonomous workflows."),
        (("framework", "checkpoint", "open-source", "release"), "Tooling improvements like this lower the effort needed to build reliable, resumable agents."),
        (("customer", "support", "retail"), "It is a concrete example of where agents are being applied and where humans stay in the loop."),
    ]

    def refine_plan(self, goal: GoalInput, default: NewsletterConfig) -> PlanRefinement:
        topic = default.topic
        return PlanRefinement(
            topic=topic,
            audience=default.audience,
            title_hint=default.title_hint,
            lookback_days=0,
            article_count=0,
            research_queries=[f"{topic}", f"{topic} launch announcement", f"{topic} enterprise adoption"],
            output_requirements=[],
            assumptions=["Deterministic test mode: plan generated by rules, no LLM call."],
        )

    def summarize(self, articles: list[Article], config: NewsletterConfig) -> list[ArticleSummary]:
        out = []
        for art in articles:
            source = art.snippet or art.source_text
            summary = first_sentences(source, 2)
            why = self._why(art)
            facts = [first_sentences(source, 1, 30)] if source else []
            out.append(ArticleSummary(article_id=art.id, summary=summary, why_it_matters=why, key_facts=facts))
        return out

    def _why(self, art: Article) -> str:
        text = (art.title + " " + art.snippet).lower()
        for keywords, sentence in self._THEMES:
            if any(k in text for k in keywords):
                return sentence
        return "It adds context on how AI agents are developing and being adopted."

    def write_editorial(
        self, config: NewsletterConfig, summaries: list[ArticleSummary], articles: list[Article], limitations: list[str]
    ) -> Editorial:
        by_id = {a.id: a for a in articles}
        lead = strip_test_prefix(by_id[summaries[0].article_id].title) if summaries else config.topic
        n = len(summaries)
        return Editorial(
            subject=f"{config.title_hint}: {n} stories on {config.topic}"[:78],
            preheader=f"This issue leads with: {lead}"[:118],
            title=config.title_hint,
            intro=(
                f"This issue collects {n} recent stories on {config.topic} for {config.audience}. "
                f"It leads with \"{lead}\" and covers the other developments selected by the research step."
            ),
            closing=(
                "Each summary links to its original source. Read the full reporting before acting on any item, "
                "and reply with topics you would like covered next time."
            ),
        )

    def critique(self, goal: str, draft: NewsletterDraft, articles: list[Article]) -> LLMCritique:
        # Rule-based reviewers in app/agent/critic.py perform the substantive checks;
        # this returns neutral model-style scores so totals stay comparable.
        return LLMCritique(goal_alignment=90, coherence=85, relevance=90, unsupported_claims=[], notes=[])

    def revise(
        self, draft: NewsletterDraft, articles: list[Article], issues: list[str], feedback: str | None
    ) -> RevisionOutput:
        by_id = {a.id: a for a in articles}
        shorter = bool(feedback and re.search(r"\b(short|shorter|concise|brief|trim)\b", feedback, re.I))
        sections = []
        for s in draft.sections:
            art = by_id.get(s.article_id)
            source = (art.snippet or art.source_text) if art else s.summary
            summary = first_sentences(source, 1 if shorter else 2)
            sections.append(
                RevisedSection(
                    article_id=s.article_id,
                    summary=summary,
                    why_it_matters=s.why_it_matters,
                    key_facts=[f for f in s.key_facts if art and _supported(f, art.source_text + " " + art.snippet)],
                )
            )
        changes = ["Rebuilt summaries extractively from source text (deterministic mode)."]
        if shorter:
            changes.append("Shortened each summary to one sentence per user feedback.")
        elif feedback:
            changes.append("User feedback recorded; deterministic mode applies only rule-based edits.")
        subject = draft.subject if len(draft.subject) <= 80 else draft.subject[:77].rsplit(" ", 1)[0] + "…"
        return RevisionOutput(
            subject=subject,
            preheader=draft.preheader[:120],
            intro=draft.intro,
            closing=draft.closing,
            sections=sections,
            changes=changes,
        )


def _supported(fact: str, source: str) -> bool:
    words = [w for w in re.findall(r"[a-z0-9]+", fact.lower()) if len(w) > 3]
    if not words:
        return True
    src = source.lower()
    return sum(1 for w in words if w in src) / len(words) >= 0.6
