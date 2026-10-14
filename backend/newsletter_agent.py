"""Convenience import for the assignment's required entry point.

    from newsletter_agent import run_newsletter_agent
    result = run_newsletter_agent("Create a weekly newsletter on latest AI agent news and send it to our subscribers.")
"""

from app.agent.runner import RunOptions, run_newsletter_agent

__all__ = ["run_newsletter_agent", "RunOptions"]
