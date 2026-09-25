from __future__ import annotations

from contextlib import AbstractAsyncContextManager
from pathlib import Path
from typing import Callable

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.cors import CORSMiddleware

from api.container import Container
from api.middleware import (
    BodySizeLimitMiddleware,
    CorrelationIdMiddleware,
    ErrorBoundaryMiddleware,
    RateLimitMiddleware,
    SecurityHeadersMiddleware,
)
from api.rate_limit import TokenBucketLimiter
from api.routes import ask, auth, documents, health, runs, sessions
from application.correlation import get_correlation_id
from application.ports.llm_provider import ProviderUnavailableError
from config.api_settings import ApiSettings
from domain.errors.domain_errors import (
    InvalidCredentialsError,
    InvalidReviewEditError,
    InvalidRunTransitionError,
    InvalidTokenError,
    PermissionDeniedError,
    TamperedRunError,
    UnapprovedDispatchError,
    UnsupportedDocumentError,
)

DESCRIPTION = """
Domain Copilot for industrial field maintenance (variant D5, twist T4).
Authenticate with `POST /auth/login`, then send `Authorization: Bearer <token>`.
Roles: **technician** (ask, raise runs), **supervisor** (approve or reject work
orders, replay), **admin** (ingest documents, view usage and audit).
"""


def _error(status: int, detail: str, headers: dict[str, str] | None = None) -> JSONResponse:
    return JSONResponse(
        status_code=status,
        content={"detail": detail, "request_id": get_correlation_id()},
        headers=headers,
    )


def create_app(
    settings: ApiSettings,
    container: Container | None = None,
    lifespan: Callable[[FastAPI], AbstractAsyncContextManager[None]] | None = None,
) -> FastAPI:
    """Tests pass a ready container; the real app builds it inside `lifespan`
    (the database pool needs a running event loop) and stores it on
    app.state.container before serving."""
    app = FastAPI(
        title="Domain Copilot API",
        version="0.1.0",
        description=DESCRIPTION,
        lifespan=lifespan,
    )
    app.state.container = container

    @app.exception_handler(InvalidCredentialsError)
    async def _bad_credentials(_: Request, exc: InvalidCredentialsError) -> JSONResponse:
        return _error(401, "invalid username or password", {"WWW-Authenticate": "Bearer"})

    @app.exception_handler(InvalidTokenError)
    async def _bad_token(_: Request, exc: InvalidTokenError) -> JSONResponse:
        return _error(401, "authentication required", {"WWW-Authenticate": "Bearer"})

    @app.exception_handler(PermissionDeniedError)
    async def _forbidden(_: Request, exc: PermissionDeniedError) -> JSONResponse:
        return _error(403, "you do not have permission to do that")

    @app.exception_handler(ProviderUnavailableError)
    async def _model_down(_: Request, exc: ProviderUnavailableError) -> JSONResponse:
        # Every configured model provider failed or timed out. Say so, and say
        # it is worth retrying; never expose provider names or upstream detail.
        return _error(
            503, "the language model is not available right now, please try again",
            {"Retry-After": "10"},
        )

    @app.exception_handler(InvalidRunTransitionError)
    async def _bad_transition(_: Request, exc: InvalidRunTransitionError) -> JSONResponse:
        return _error(409, "that run is not in a state that allows this action")

    @app.exception_handler(UnapprovedDispatchError)
    async def _not_approved(_: Request, exc: UnapprovedDispatchError) -> JSONResponse:
        return _error(409, "the work order is not in a state that allows this action")

    @app.exception_handler(InvalidReviewEditError)
    async def _bad_edit(_: Request, exc: InvalidReviewEditError) -> JSONResponse:
        return _error(422, str(exc))

    @app.exception_handler(TamperedRunError)
    async def _tampered(_: Request, exc: TamperedRunError) -> JSONResponse:
        return _error(409, "the audit log for this run failed hash-chain verification")

    @app.exception_handler(UnsupportedDocumentError)
    async def _bad_document(_: Request, exc: UnsupportedDocumentError) -> JSONResponse:
        return _error(422, str(exc))

    @app.get("/", include_in_schema=False)
    async def _home() -> RedirectResponse:
        return RedirectResponse("/ui/")

    app.include_router(health.router)
    app.include_router(auth.router)
    app.include_router(ask.router)
    app.include_router(sessions.router)
    app.include_router(runs.router)
    app.include_router(documents.router)

    # The bundled web UI: static files only, no server-side templating. It is
    # served under /ui, which the security middleware knows about (CSP).
    app.mount("/ui", StaticFiles(directory=Path(__file__).parent / "static", html=True), name="ui")

    # Added innermost first; the last one added is the outermost.
    app.add_middleware(ErrorBoundaryMiddleware)
    if settings.cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=list(settings.cors_origins),
            allow_methods=["GET", "POST", "DELETE"],
            allow_headers=["Authorization", "Content-Type", "X-Request-ID"],
        )
    app.add_middleware(
        BodySizeLimitMiddleware,
        max_bytes=settings.max_body_bytes,
        upload_max_bytes=settings.upload_max_bytes,
    )
    app.add_middleware(
        RateLimitMiddleware, limiter=TokenBucketLimiter(settings.rate_limit_per_minute)
    )
    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(CorrelationIdMiddleware)
    return app
