"""Command-line runner.

    python -m app.cli "Create a weekly newsletter on the latest AI agent news" [--deterministic] [--mode hitl]

In Human-in-the-Loop mode the CLI pauses and asks YOU to approve the article
selection and the draft; nothing is approved automatically.
"""

from __future__ import annotations

import argparse
import json
import sys

from app.agent.runner import RunOptions, run_newsletter_agent
from app.models.domain import ExecutionMode

DEFAULT_GOAL = "Create a weekly newsletter on the latest AI agent news and send it to our subscribers."


def console_approval(payload: dict) -> dict:
    if payload["kind"] == "research":
        cands = payload["candidates"]
        proposed = set(payload["proposed_ids"])
        print("\nProposed articles (* = selected):")
        for i, c in enumerate(cands, 1):
            mark = "*" if c["id"] in proposed else " "
            print(f" {mark} [{i}] {c['title'][:90]}  ({c['publisher']}, {c.get('published_date') or 'date unavailable'})")
        raw = input("Press Enter to approve, or type numbers to select (e.g. 1,3,4): ").strip()
        if not raw:
            return {"action": "approve", "selected_ids": list(payload["proposed_ids"])}
        picks = [int(x) for x in raw.replace(" ", "").split(",") if x.isdigit() and 1 <= int(x) <= len(cands)]
        return {"action": "approve", "selected_ids": [cands[i - 1]["id"] for i in picks][:7]}
    draft, review = payload["draft"], payload["review"]
    print(f"\nDraft subject: {draft['subject']}\nReview: {review['score']}/100 - {review['summary']}")
    for s in draft["sections"]:
        print(f" - {s['headline'][:90]}")
    raw = input("Press Enter to approve, or type revision feedback: ").strip()
    return {"action": "approve"} if not raw else {"action": "revise", "feedback": raw}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the Newsletter Agent")
    parser.add_argument("goal", nargs="?", default=DEFAULT_GOAL)
    parser.add_argument("--deterministic", action="store_true", help="Offline run on labelled fixture data")
    parser.add_argument("--mode", choices=["autonomous", "hitl"], default="autonomous")
    parser.add_argument("--articles", type=int, default=None)
    parser.add_argument("--days", type=int, default=None)
    parser.add_argument("--json", action="store_true", help="Print the full JSON result")
    args = parser.parse_args(argv)

    mode = ExecutionMode.HUMAN_IN_THE_LOOP if args.mode == "hitl" else ExecutionMode.AUTONOMOUS
    result = run_newsletter_agent(
        args.goal,
        RunOptions(
            mode=mode,
            deterministic=args.deterministic,
            article_count=args.articles,
            lookback_days=args.days,
            approval_handler=console_approval if mode == ExecutionMode.HUMAN_IN_THE_LOOP else None,
            echo=not args.json,
        ),
    )
    if args.json:
        print(json.dumps(result.model_dump(mode="json", exclude={"html", "markdown"}), indent=2))
    else:
        print(f"\nStatus: {result.status.value}")
        if result.error:
            print(f"Error: {result.error}")
        if result.subject:
            print(f"Subject: {result.subject}")
        if result.review:
            print(f"Review: {result.review.score}/100 ({'passed' if result.review.passed else 'not passed'})")
        if result.html_path:
            print(f"HTML: {result.html_path}\nMarkdown: {result.markdown_path}")
        print(result.delivery_note)
        if result.markdown:
            print("\n" + "=" * 72 + "\n" + result.markdown)
    return 0 if result.status.value.startswith("completed") else 1


if __name__ == "__main__":
    sys.exit(main())
