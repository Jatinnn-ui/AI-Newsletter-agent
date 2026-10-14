"""Low-level structured-output LLM client (Google Gen AI SDK).

`GeminiJSONClient.generate_json` asks Gemini for JSON matching a Pydantic
schema and validates the response. Resilience rules:

* Per-minute rate limits (429) and overload (503/504): wait (honouring the
  server's retry delay, capped) and retry the same model.
* Daily quota exhausted (429 with a *PerDay* quota): stop using that model
  until the quota resets and switch to the next model in the fallback list.
* Model not found (404): switch to the next model.
* Bad key (401/403): fail immediately with a clear message.
* Malformed JSON: re-prompt once.
"""

from __future__ import annotations

import random
import re
import threading
import time
from dataclasses import dataclass
from typing import Any, Protocol, TypeVar

from pydantic import BaseModel, ValidationError

from app.services.telemetry import redact

T = TypeVar("T", bound=BaseModel)

MAX_WAIT_SECONDS = 30.0


class LLMError(Exception):
    """Raised when the LLM cannot produce a valid response."""


class LLMConfigurationError(LLMError):
    pass


class LLMRateLimitError(LLMError):
    pass


class JSONModelClient(Protocol):
    def generate_json(self, *, system: str, prompt: str, schema: type[T], temperature: float = 0.3) -> T: ...


@dataclass
class QuotaInfo:
    per_day: bool
    retry_seconds: float | None
    limit: str | None


def parse_quota(exc: Any) -> QuotaInfo:
    """Extract quota type and retry delay from a google-genai APIError."""
    details = getattr(exc, "details", None)
    items = []
    if isinstance(details, dict):
        items = (details.get("error") or {}).get("details") or []
    per_day, retry, limit = False, None, None
    for item in items if isinstance(items, list) else []:
        if not isinstance(item, dict):
            continue
        kind = str(item.get("@type", ""))
        if "QuotaFailure" in kind:
            for v in item.get("violations") or []:
                quota_id = str(v.get("quotaId", ""))
                if "PerDay" in quota_id:
                    per_day = True
                if v.get("quotaValue") is not None:
                    limit = f"{v['quotaValue']} requests/{'day' if 'PerDay' in quota_id else 'minute'}"
        if "RetryInfo" in kind:
            m = re.match(r"^(\d+(?:\.\d+)?)s$", str(item.get("retryDelay", "")))
            if m:
                retry = float(m.group(1))
    if not items and "per day" in str(exc).lower():
        per_day = True
    return QuotaInfo(per_day=per_day, retry_seconds=retry, limit=limit)


def _fmt_duration(seconds: float) -> str:
    if seconds >= 3600:
        return f"{seconds / 3600:.0f}h"
    if seconds >= 60:
        return f"{seconds / 60:.0f}min"
    return f"{seconds:.0f}s"


class _ExhaustedModels:
    """Process-wide memory of models whose daily quota ran out (shared by all runs)."""

    def __init__(self) -> None:
        self._until: dict[str, float] = {}
        self._lock = threading.Lock()

    def mark(self, model: str, seconds: float | None) -> None:
        with self._lock:
            self._until[model] = time.monotonic() + (seconds if seconds and seconds > 0 else 3600)

    def is_exhausted(self, model: str) -> bool:
        with self._lock:
            until = self._until.get(model)
            if until is None:
                return False
            if time.monotonic() >= until:
                del self._until[model]
                return False
            return True

    def clear(self) -> None:
        with self._lock:
            self._until.clear()


EXHAUSTED = _ExhaustedModels()


class GeminiJSONClient:
    def __init__(
        self,
        api_key: str | None,
        model: str,
        *,
        fallback_models: list[str] | None = None,
        timeout_seconds: float = 60.0,
        max_retries: int = 3,
        client: object | None = None,
        sleep=time.sleep,
    ) -> None:
        if client is None:
            if not api_key:
                raise LLMConfigurationError(
                    "GEMINI_API_KEY is not configured. Set it in the backend environment or use deterministic test mode."
                )
            from google import genai
            from google.genai import types

            client = genai.Client(
                api_key=api_key,
                http_options=types.HttpOptions(timeout=int(timeout_seconds * 1000)),
            )
        self._client = client
        self.model = model
        self.models = list(dict.fromkeys([model, *(fallback_models or [])]))
        self._max_retries = max_retries
        self._sleep = sleep
        self.last_model: str | None = None

    def generate_json(self, *, system: str, prompt: str, schema: type[T], temperature: float = 0.3) -> T:
        from google.genai import types

        config = types.GenerateContentConfig(
            system_instruction=system,
            response_mime_type="application/json",
            response_schema=schema,
            temperature=temperature,
        )
        problems: list[str] = []
        candidates = [m for m in self.models if not EXHAUSTED.is_exhausted(m)]
        skipped = [m for m in self.models if m not in candidates]
        for m in skipped:
            problems.append(f"{m}: daily free-tier quota used up earlier")
        rate_limited = bool(skipped)

        for model in candidates:
            try:
                result = self._call_model(model, prompt, config, schema)
                self.last_model = model
                return result
            except _SwitchModel as switch:
                problems.append(f"{model}: {switch.reason}")
                rate_limited = rate_limited or switch.rate_limited
                continue

        summary = "; ".join(problems) or "no models configured"
        if rate_limited:
            raise LLMRateLimitError(
                f"Gemini quota/rate limit reached for every configured model ({summary}). "
                "Free-tier daily quotas reset after ~24h; add more models to GEMINI_FALLBACK_MODELS or use a paid key."
            )
        raise LLMError(f"Gemini request failed for every configured model ({summary}).")

    def _call_model(self, model: str, prompt: str, config: Any, schema: type[T]) -> T:
        from google.genai import errors

        contents = prompt
        malformed_retry_used = False
        attempt = 0
        while True:
            try:
                response = self._client.models.generate_content(model=model, contents=contents, config=config)
            except errors.APIError as exc:
                code = getattr(exc, "code", None) or 0
                if code in (401, 403):
                    raise LLMConfigurationError("Gemini rejected the API key (check GEMINI_API_KEY).") from exc
                if code == 404:
                    raise _SwitchModel("model not found for this key")
                if code == 429:
                    quota = parse_quota(exc)
                    if quota.per_day:
                        EXHAUSTED.mark(model, quota.retry_seconds)
                        reset = f", resets in ~{_fmt_duration(quota.retry_seconds)}" if quota.retry_seconds else ""
                        raise _SwitchModel(f"daily free-tier quota used up ({quota.limit or 'limit reached'}{reset})", True)
                    if attempt < self._max_retries:
                        wait = quota.retry_seconds or (2**attempt + random.random())
                        self._sleep(min(wait, MAX_WAIT_SECONDS))
                        attempt += 1
                        continue
                    raise _SwitchModel(f"rate limited ({quota.limit or 'per-minute limit'})", True)
                if code >= 500:
                    if attempt < self._max_retries:
                        self._sleep(min(2**attempt + random.random(), MAX_WAIT_SECONDS))
                        attempt += 1
                        continue
                    raise _SwitchModel(f"server busy (HTTP {code})")
                raise LLMError(f"Gemini API error (HTTP {code}): {redact(str(exc), 200)}") from exc
            except Exception as exc:  # network errors from the SDK transport
                if attempt < self._max_retries:
                    self._sleep(min(2**attempt + random.random(), MAX_WAIT_SECONDS))
                    attempt += 1
                    continue
                raise _SwitchModel(f"request failed ({type(exc).__name__})") from exc

            text = getattr(response, "text", None) or ""
            try:
                return schema.model_validate_json(_strip_fences(text))
            except (ValidationError, ValueError):
                if malformed_retry_used:
                    raise _SwitchModel("returned malformed JSON twice")
                malformed_retry_used = True
                contents = (
                    prompt
                    + "\n\nYour previous reply was not valid JSON for the required schema. "
                    "Reply again with ONLY a JSON object that matches the schema exactly."
                )


class _SwitchModel(Exception):
    def __init__(self, reason: str, rate_limited: bool = False) -> None:
        super().__init__(reason)
        self.reason = reason
        self.rate_limited = rate_limited


def _strip_fences(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else ""
        if text.rstrip().endswith("```"):
            text = text.rstrip()[:-3]
    return text.strip()
