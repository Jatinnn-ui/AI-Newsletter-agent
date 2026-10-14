"""Application configuration loaded from environment variables.

Secrets (API keys) are only ever read here and are never logged or returned
by the API. Use `Settings.public_summary()` for anything user-facing.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(BACKEND_DIR.parent / ".env", BACKEND_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- Environment -----------------------------------------------------
    app_env: str = Field(default="development", description="development | production")

    # --- AI provider ------------------------------------------------------
    gemini_api_key: str | None = None
    gemini_model: str = "gemini-2.5-flash"
    # Tried in order when the primary model is rate limited, out of daily quota, overloaded or unavailable.
    # Each model has its own free-tier quota, so this multiplies the free daily capacity.
    gemini_fallback_models: str = "gemini-2.5-flash-lite,gemini-3.5-flash-lite"
    llm_timeout_seconds: float = 60.0
    llm_max_retries: int = Field(default=3, ge=0, le=6)

    # --- Research provider -----------------------------------------------
    tavily_api_key: str | None = None
    tavily_search_depth: str = "basic"
    search_max_results_per_query: int = Field(default=8, ge=1, le=20)
    search_max_queries: int = Field(default=4, ge=1, le=6)
    search_timeout_seconds: float = 20.0
    retrieval_timeout_seconds: float = 8.0
    retrieval_max_bytes: int = 1_500_000
    retrieval_max_articles: int = Field(default=10, ge=0, le=15)

    # --- Deterministic test mode ------------------------------------------
    # When true, every run uses fixture search data and a rule-based LLM.
    deterministic_mode: bool = False
    # When true, a client may request a deterministic run per request.
    allow_deterministic_runs: bool = True

    # --- Workflow limits ---------------------------------------------------
    max_revisions: int = Field(default=2, ge=0, le=2)
    max_user_revisions: int = Field(default=3, ge=0, le=5)
    review_pass_threshold: int = Field(default=80, ge=0, le=100)
    max_run_seconds: int = Field(default=600, ge=30)

    # --- Run management ----------------------------------------------------
    max_concurrent_runs: int = Field(default=2, ge=1, le=8)
    max_pending_runs: int = Field(default=8, ge=1, le=50)
    approval_ttl_hours: float = 24.0
    run_retention_days: float = 7.0
    cleanup_interval_seconds: int = 300

    # --- Storage -----------------------------------------------------------
    output_dir: Path = BACKEND_DIR / "output"
    data_dir: Path = BACKEND_DIR / "data"

    # --- HTTP --------------------------------------------------------------
    # When set, every /api route except /api/health requires this token
    # (Authorization: Bearer <token>, X-API-Key, or ?access_token= for SSE/downloads).
    api_auth_token: str | None = None
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"
    max_request_bytes: int = 64_000

    @field_validator("gemini_api_key", "tavily_api_key", "api_auth_token", mode="before")
    @classmethod
    def _blank_to_none(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = str(value).strip()
        if not value or value.lower().startswith("your_") or value == "changeme":
            return None
        return value

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip().rstrip("/") for o in self.cors_origins.split(",") if o.strip()]

    @property
    def gemini_fallback_list(self) -> list[str]:
        return [m.strip() for m in self.gemini_fallback_models.split(",") if m.strip() and m.strip() != self.gemini_model]

    @property
    def gemini_configured(self) -> bool:
        return bool(self.gemini_api_key)

    @property
    def tavily_configured(self) -> bool:
        return bool(self.tavily_api_key)

    @property
    def live_mode_available(self) -> bool:
        return self.gemini_configured and self.tavily_configured

    def public_summary(self) -> dict:
        """Configuration status that is safe to expose (no secret values)."""
        return {
            "environment": self.app_env,
            "llm_provider": "gemini",
            "llm_model": self.gemini_model,
            "llm_fallback_models": self.gemini_fallback_list,
            "llm_configured": self.gemini_configured,
            "search_provider": "tavily",
            "search_configured": self.tavily_configured,
            "deterministic_mode": self.deterministic_mode,
            "deterministic_runs_allowed": self.allow_deterministic_runs or self.deterministic_mode,
            "live_mode_available": self.live_mode_available,
            "max_revisions": self.max_revisions,
            "review_pass_threshold": self.review_pass_threshold,
            "delivery_mode": "simulated",
            "auth_required": bool(self.api_auth_token),
        }


@lru_cache
def get_settings() -> Settings:
    return Settings()
