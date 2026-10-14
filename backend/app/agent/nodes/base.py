"""Shared node wrapper: stage events, cancellation checks and failure capture."""

from __future__ import annotations

import functools
from typing import Any, Callable

from langgraph.errors import GraphBubbleUp

from app.agent.services import AgentServices, ConfigurationError
from app.agent.state import AgentState
from app.models.domain import Article
from app.services.llm import LLMError
from app.services.telemetry import NodeContext, RunCancelled, RunTimedOut, redact
from app.storage.base import StorageError
from app.tools.web_search import SearchError

NodeFn = Callable[[AgentState, NodeContext, AgentServices], dict[str, Any]]


class WorkflowError(Exception):
    """A handled failure with a user-facing message."""


def llm_reason(exc: Exception) -> str:
    """Short, plain-language reason for an LLM fallback (shown in the UI)."""
    from app.services.llm import LLMConfigurationError, LLMRateLimitError

    if isinstance(exc, LLMRateLimitError):
        return "Gemini's free usage limit was reached (it resets daily)"
    if isinstance(exc, LLMConfigurationError):
        return "Gemini rejected the request (check the API key/model)"
    return "Gemini did not respond"


def user_message(exc: Exception) -> str:
    if isinstance(exc, SearchError):
        return f"{exc} {exc.recovery}"
    if isinstance(exc, (LLMError, StorageError, WorkflowError, ConfigurationError, ValueError)):
        return redact(str(exc), 400)
    return f"Unexpected {type(exc).__name__}: {redact(str(exc), 300)}"


def agent_node(stage: str) -> Callable[[NodeFn], Callable[[AgentServices], Callable[[AgentState], dict]]]:
    """Decorate `fn(state, ctx, services)` into a LangGraph node factory."""

    def decorator(fn: NodeFn) -> Callable[[AgentServices], Callable[[AgentState], dict]]:
        @functools.wraps(fn)
        def factory(services: AgentServices) -> Callable[[AgentState], dict]:
            def run(state: AgentState) -> dict:
                ctx = NodeContext(run_id=state["run_id"], stage=stage, reporter=services.reporter)
                ctx.check_cancelled()
                ctx.stage_event("running")
                try:
                    update = fn(state, ctx, services) or {}
                except (GraphBubbleUp, RunCancelled, RunTimedOut):
                    raise
                except Exception as exc:
                    message = user_message(exc)
                    ctx.log(f"{stage.capitalize()} failed: {message}", "error")
                    ctx.stage_event("failed", message, stage=ctx.stage)
                    return {**ctx.flush(), "status": "failed", "error": message}
                if not update.pop("_keep_stage_open", False):
                    ctx.stage_event("completed", stage=ctx.stage)
                return {**update, **ctx.flush()}

            run.__name__ = fn.__name__
            return run

        return factory

    return decorator


def articles_by_id(state: AgentState) -> dict[str, Article]:
    return {a["id"]: Article.model_validate(a) for a in state.get("candidates", [])}
