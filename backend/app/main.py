"""FastAPI application entry point.

Run locally:  uvicorn app.main:app --reload --port 8000   (from backend/)
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

# Static frontend build, if bundled into the image (combined backend+frontend deploy).
STATIC_DIR = Path(__file__).resolve().parent / "static"

from app import __version__
from app.api.routes import protected, router
from app.config import Settings, get_settings
from app.services.run_manager import RunManager

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


def create_app(settings: Settings | None = None, manager: RunManager | None = None) -> FastAPI:
    settings = settings or get_settings()
    # Auth is optional: if API_AUTH_TOKEN is unset, the API is open (auth_required=false)
    # and no token prompt is shown. Set a token to protect the API again.
    if settings.app_env == "production" and not settings.api_auth_token:
        logging.getLogger("app").warning(
            "APP_ENV=production without API_AUTH_TOKEN: the API is UNPROTECTED. Anyone with the URL can start runs and spend your LLM/search quota. Set API_AUTH_TOKEN to re-enable auth."
        )

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.manager = manager or RunManager(settings)
        try:
            yield
        finally:
            app.state.manager.shutdown()

    app = FastAPI(
        title="Newsletter Agent API",
        version=__version__,
        description="Autonomous AI newsletter agent (LangGraph + Gemini + Tavily). Delivery is simulated.",
        lifespan=lifespan,
    )
    app.state.settings = settings

    origins = settings.cors_origin_list
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=False,  # no cookies/auth headers are used; never combine credentials with wildcard
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["Content-Type", "Last-Event-ID", "Authorization", "X-API-Key"],
        max_age=600,
    )

    @app.middleware("http")
    async def limit_body_size(request: Request, call_next):
        if request.method == "POST":
            length = request.headers.get("content-length")
            if length is not None and (not length.isdigit() or int(length) > settings.max_request_bytes):
                return JSONResponse({"detail": "Request body too large."}, status_code=413)
            # Content-Length is only an early rejection. Read the actual ASGI body
            # with a hard cap too, so chunked/no-length requests cannot bypass it.
            body = bytearray()
            async for chunk in request.stream():
                body.extend(chunk)
                if len(body) > settings.max_request_bytes:
                    return JSONResponse({"detail": "Request body too large."}, status_code=413)
            request._body = bytes(body)  # Starlette replays this cached body to the route.
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        return response

    @app.exception_handler(RequestValidationError)
    async def validation_error(_: Request, exc: RequestValidationError):
        errors = [
            {"field": ".".join(str(p) for p in e.get("loc", [])[1:]) or "body", "message": e.get("msg", "Invalid value")}
            for e in exc.errors()
        ]
        return JSONResponse({"detail": "Invalid request.", "errors": errors}, status_code=422)

    app.include_router(router)
    app.include_router(protected)

    index_file = STATIC_DIR / "index.html"
    frontend_bundled = index_file.is_file()

    if not frontend_bundled:
        @app.get("/", include_in_schema=False)
        def root():
            return {"name": "Newsletter Agent API", "docs": "/docs", "health": "/api/health"}
    else:
        # Serve hashed build assets with long-lived caching.
        assets_dir = STATIC_DIR / "assets"
        if assets_dir.is_dir():
            app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")

        @app.get("/", include_in_schema=False)
        def spa_root():
            return FileResponse(index_file)

        # SPA fallback: any non-API path returns index.html so client-side routing works.
        @app.get("/{full_path:path}", include_in_schema=False)
        def spa_fallback(full_path: str):
            candidate = (STATIC_DIR / full_path).resolve()
            # Only serve files that actually live inside the static dir (no traversal).
            if STATIC_DIR in candidate.parents and candidate.is_file():
                return FileResponse(candidate)
            return FileResponse(index_file)

    return app


app = create_app()
