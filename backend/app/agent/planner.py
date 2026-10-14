"""Node A helpers: heuristic goal interpretation and plan construction.

The heuristic always runs first so the plan has sensible defaults; the LLM
may refine topic, audience and queries. Explicit user settings always win.
"""

from __future__ import annotations

import re

from app.agent.llm_tasks import PlanRefinement
from app.models.domain import ExecutionPlan, GoalInput, NewsletterConfig, PlanTask, Stage

DEFAULT_TOPIC = "AI agents"
DEFAULT_AUDIENCE = "technology professionals and newsletter subscribers"
DEFAULT_COUNT = 5
DEFAULT_LOOKBACK = 7

_CADENCE = {"daily": 1, "weekly": 7, "biweekly": 14, "fortnightly": 14, "monthly": 30}
_WORD_NUM = {"three": 3, "four": 4, "five": 5, "six": 6, "seven": 7}


def _extract_topic(goal: str) -> str | None:
    patterns = [
        r"\b(?:on|about|covering|regarding)\s+(?:the\s+)?(?:latest|recent|top|current|this week'?s?)?\s*(.+?)"
        r"(?:\s+(?:news|developments|updates|stories|headlines))?(?:\s+(?:and|for|to|from|in|that|which)\b|[.,;!?]|$)",
        r"\b(?:latest|recent)\s+(.+?)\s+(?:news|developments|updates)\b",
    ]
    for pat in patterns:
        m = re.search(pat, goal, re.I)
        if m:
            topic = m.group(1).strip(" .,'\"")
            topic = re.sub(r"\b(news|newsletter|developments|updates|the|latest|recent)\b", "", topic, flags=re.I)
            topic = re.sub(r"\s+", " ", topic).strip()
            if 2 <= len(topic) <= 80:
                return topic
    return None


def _extract_audience(goal: str) -> str | None:
    m = re.search(r"\bfor\s+(?:our\s+|my\s+|the\s+)?([a-z][\w\s-]{2,60}?)(?:[.,;!?]|\s+and\b|\s+about\b|$)", goal, re.I)
    if m and not re.match(r"(?i)(the\s+)?(week|month|day|last|past)", m.group(1)):
        return m.group(1).strip()
    if re.search(r"\bsubscribers\b", goal, re.I):
        return "newsletter subscribers interested in technology"
    return None


def _extract_lookback(goal: str) -> int | None:
    m = re.search(r"\b(?:last|past)\s+(\d{1,2})\s+days?\b", goal, re.I)
    if m:
        return max(1, min(int(m.group(1)), 31))
    if re.search(r"\b(?:last|past)\s+(?:week|7 days)\b", goal, re.I):
        return 7
    if re.search(r"\b(?:last|past)\s+month\b", goal, re.I):
        return 30
    for word, days in _CADENCE.items():
        if re.search(rf"\b{word}\b", goal, re.I):
            return days
    return None


def _extract_count(goal: str) -> int | None:
    m = re.search(r"\b(?:top\s+)?(\d|three|four|five|six|seven)(?:\s*-\s*\d)?\s+(?:articles|stories|items|links)\b", goal, re.I)
    if m:
        raw = m.group(1).lower()
        value = _WORD_NUM.get(raw) or int(raw)
        return max(3, min(value, 7))
    return None


def _cadence_label(days: int) -> str:
    return {1: "daily", 7: "weekly", 14: "biweekly", 30: "monthly"}.get(days, f"{days}-day")


def heuristic_config(goal: GoalInput) -> tuple[NewsletterConfig, list[str]]:
    assumptions: list[str] = []
    topic = goal.topic or _extract_topic(goal.goal)
    if not topic:
        topic = DEFAULT_TOPIC
        assumptions.append(f"No clear topic found in the goal; defaulted to '{DEFAULT_TOPIC}'.")
    audience = goal.audience or _extract_audience(goal.goal) or DEFAULT_AUDIENCE
    lookback = goal.lookback_days or _extract_lookback(goal.goal)
    if lookback is None:
        lookback = DEFAULT_LOOKBACK
        assumptions.append(f"No time window specified; using the last {DEFAULT_LOOKBACK} days.")
    count = goal.article_count or _extract_count(goal.goal)
    if count is None:
        count = DEFAULT_COUNT
        assumptions.append(f"No article count specified; targeting {DEFAULT_COUNT} stories.")
    cadence = _cadence_label(lookback)
    title = f"{_title_case(topic)} {cadence.capitalize() if cadence.isalpha() else 'Brief'}"
    return (
        NewsletterConfig(
            topic=topic, audience=audience, article_count=count, lookback_days=lookback, cadence=cadence,
            title_hint=title[:60],
        ),
        assumptions,
    )


def _title_case(text: str) -> str:
    words = []
    for w in text.split():
        if w.lower() in {"ai", "ml", "llm", "llms"}:
            words.append(w.upper())
        else:
            words.append(w[:1].upper() + w[1:])
    return " ".join(words)


def default_queries(topic: str) -> list[str]:
    return [f"{topic} news", f"{topic} launch announcement", f"{topic} enterprise adoption research"]


def build_plan(
    goal: GoalInput,
    config: NewsletterConfig,
    assumptions: list[str],
    refinement: PlanRefinement | None,
    planner: str,
    max_queries: int,
) -> ExecutionPlan:
    queries = default_queries(config.topic)
    requirements: list[str] = []
    if refinement is not None:
        if not goal.topic and refinement.topic.strip():
            config.topic = refinement.topic.strip()[:120]
        if not goal.audience and refinement.audience.strip():
            config.audience = refinement.audience.strip()[:120]
        if refinement.title_hint.strip():
            config.title_hint = refinement.title_hint.strip()[:60]
        if not goal.lookback_days and 1 <= refinement.lookback_days <= 31:
            config.lookback_days = refinement.lookback_days
        if not goal.article_count and 3 <= refinement.article_count <= 7:
            config.article_count = refinement.article_count
        cleaned = [re.sub(r"\s+", " ", q).strip()[:200] for q in refinement.research_queries if q.strip()]
        if cleaned:
            queries = cleaned
        requirements = [r.strip()[:200] for r in refinement.output_requirements if r.strip()][:5]
        assumptions = assumptions + [a.strip()[:200] for a in refinement.assumptions if a.strip()][:3]
    seen: set[str] = set()
    unique = []
    for q in queries:
        if q.lower() not in seen:
            seen.add(q.lower())
            unique.append(q)
    queries = unique[:max_queries]

    requirements = requirements or []
    requirements = [
        f"{config.article_count} stories (5-7 when enough credible sources exist; never filler)",
        f"Only stories published within the last {config.lookback_days} days when dates are available",
        "Each story: headline, publisher, verified date or 'unavailable', summary, why it matters, source link",
        "Email-safe HTML plus Markdown, saved to file; delivery is simulated",
    ] + requirements

    c = config
    tasks = [
        PlanTask(id="t1", stage=Stage.PLANNING, title="Interpret goal",
                 description=f"Topic '{c.topic}', audience '{c.audience}', {c.lookback_days}-day window."),
        PlanTask(id="t2", stage=Stage.RESEARCH, title="Research news",
                 description=f"Run {len(queries)} web searches, normalize, deduplicate and retrieve articles."),
        PlanTask(id="t3", stage=Stage.SELECTION, title="Rank and select",
                 description=f"Rank by relevance, recency, source quality and diversity; pick {c.article_count}."),
        PlanTask(id="t4", stage=Stage.SUMMARIZATION, title="Summarize",
                 description="Summarize each story from retrieved text and explain why it matters."),
        PlanTask(id="t5", stage=Stage.WRITING, title="Write newsletter",
                 description="Write subject, preheader, intro and closing; render HTML and Markdown."),
        PlanTask(id="t6", stage=Stage.REVIEW, title="Self-review",
                 description="Score the draft against explicit quality checks."),
        PlanTask(id="t7", stage=Stage.REVISION, title="Revise if needed",
                 description="Fix correctable issues (max 2 automatic revisions)."),
        PlanTask(id="t8", stage=Stage.OUTPUT, title="Save and simulate delivery",
                 description="Save HTML and Markdown files; delivery is simulated."),
    ]
    if goal.mode.value == "human_in_the_loop":
        tasks.insert(3, PlanTask(id="h1", stage=Stage.SELECTION, title="Human approval: articles",
                                 description="Pause for the user to approve or edit the article selection."))
        tasks.insert(-1, PlanTask(id="h2", stage=Stage.OUTPUT, title="Human approval: draft",
                                  description="Pause for the user to approve the draft or request a revision."))
    summary = (
        f"Produce a {c.cadence} newsletter on {c.topic} for {c.audience}, covering {c.article_count} stories "
        f"from the last {c.lookback_days} days."
    )
    return ExecutionPlan(
        normalized_goal=goal.goal,
        summary=summary,
        tasks=tasks,
        research_queries=queries,
        output_requirements=requirements,
        assumptions=assumptions,
        config=config,
        planner=planner,  # type: ignore[arg-type]
    )
