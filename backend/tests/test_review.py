"""11. Reviewer detects missing sources  12. Revision loop and retry limit"""

from datetime import date

from app.agent.critic import review_draft, unsupported_numbers
from app.agent.llm_tasks import DeterministicAgentLLM, LLMCritique
from app.agent.runner import RunOptions, run_newsletter_agent
from app.models.domain import ArticleSummary, RunStatus
from app.tools.newsletter_renderer import render_newsletter
from tests.conftest import GOAL
from tests.test_writing import _draft


def _review(draft, articles, llm=None):
    return review_draft(
        goal=GOAL, topic="AI agents", requested_count=len(draft.sections), draft=draft,
        articles={a.id: a for a in articles}, validation=render_newsletter(draft).validation,
        llm=llm or LLMCritique(goal_alignment=90, coherence=90, relevance=90), attempt=1, threshold=80,
        today=date.today(),
    )


def test_clean_draft_passes(fixture_articles):
    arts = fixture_articles[:5]
    review = _review(_draft(arts), arts)
    assert review.passed and not review.critical_issues
    assert {c.id for c in review.checks} >= {"source_links", "dates", "duplicates", "html_valid", "supported_claims"}


def test_missing_source_is_critical_and_blocks_pass_despite_high_average(fixture_articles):
    arts = fixture_articles[:5]
    draft = _draft(arts)
    draft.sections[0].source_url = ""
    review = _review(draft, arts)
    assert review.score >= 80  # average alone would pass...
    assert not review.passed  # ...but critical source failure blocks it
    assert any(i.check_id == "source_links" and i.severity == "critical" for i in review.issues)


def test_url_not_from_research_is_flagged(fixture_articles):
    arts = fixture_articles[:3]
    draft = _draft(arts)
    draft.sections[1].source_url = "https://made-up.example/invented"
    assert any("does not match" in i.message for i in _review(draft, arts).issues)


def test_wrong_date_duplicates_and_delivery_claims_flagged(fixture_articles):
    arts = fixture_articles[:4]
    draft = _draft(arts, intro="This newsletter has been sent to all subscribers already this week.")
    draft.sections[0].published_date = "2099-01-01"
    draft.sections[2].source_url = draft.sections[1].source_url
    draft.sections[2].article_id = draft.sections[1].article_id
    review = _review(draft, arts)
    checks = {i.check_id for i in review.issues}
    assert {"dates", "duplicates", "structure"} <= checks
    assert not review.passed


def test_unsupported_numbers_and_llm_claims_detected(fixture_articles):
    assert unsupported_numbers("Revenue grew 73% to $4.2 billion", "Revenue grew strongly") == ["4.2", "73%"]
    assert unsupported_numbers("A survey of 400 companies", "survey of 400 companies") == []
    arts = fixture_articles[:3]
    draft = _draft(arts)
    draft.sections[0].summary = "The company says 87% of users adopted it within 12 weeks of launch."
    llm = LLMCritique(goal_alignment=90, coherence=90, relevance=90,
                      unsupported_claims=[{"article_id": arts[1].id, "claim": "X", "reason": "not in source"}])
    review = _review(draft, arts, llm)
    claims = [i for i in review.issues if i.check_id == "supported_claims"]
    assert len(claims) == 2 and review.revision_required


class InventsNumbersLLM(DeterministicAgentLLM):
    """Summarizer that adds an unsupported statistic; revision fixes it (deterministic revise)."""

    def summarize(self, articles, config):
        out = super().summarize(articles, config)
        out[0] = ArticleSummary(**{**out[0].model_dump(), "summary": out[0].summary + " Adoption rose 87% in 2026."})
        return out


class StubbornLLM(InventsNumbersLLM):
    def revise(self, draft, articles, issues, feedback):
        out = super().revise(draft, articles, issues, feedback)
        out.sections[0].summary += " Adoption rose 87% in 2026."
        return out


def test_revision_loop_fixes_correctable_issue(make_services):
    result = run_newsletter_agent(GOAL, RunOptions(deterministic=True,
                                                   services_factory=lambda r: make_services(r, llm=InventsNumbersLLM())))
    assert result.status == RunStatus.COMPLETED
    assert len(result.reviews) == 2 and result.reviews[0].revision_required
    assert len(result.revisions) == 1 and result.revisions[0].trigger == "critic"
    assert result.revisions[0].score_after is not None and result.review.passed


def test_revision_limit_is_enforced_and_warning_returned(make_services):
    result = run_newsletter_agent(GOAL, RunOptions(deterministic=True,
                                                   services_factory=lambda r: make_services(r, llm=StubbornLLM())))
    assert len(result.revisions) == 2  # max_revisions
    assert len(result.reviews) == 3
    assert result.status == RunStatus.COMPLETED_WITH_WARNINGS  # honest warning, not success
    assert result.review.revision_required  # still flagged; not inflated away
    assert any("Unresolved" in w and "87%" in w for w in result.warnings)
