"""Optional shared-token authentication for the API.

Enabled by setting API_AUTH_TOKEN. Accepted credentials (first match wins):
  * Authorization: Bearer <token>
  * X-API-Key: <token>
Comparison is constant-time. /api/health stays public for uptime checks.
"""

from __future__ import annotations

import hmac

from fastapi import HTTPException, Request, status


def require_auth(request: Request) -> None:
    expected = request.app.state.settings.api_auth_token
    if not expected:
        return
    supplied = None
    header = request.headers.get("authorization", "")
    if header.lower().startswith("bearer "):
        supplied = header[7:].strip()
    supplied = supplied or request.headers.get("x-api-key")
    if not supplied or not hmac.compare_digest(supplied.encode(), expected.encode()):
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "Missing or invalid API token. Enter the API token in Settings.",
            headers={"WWW-Authenticate": "Bearer"},
        )
