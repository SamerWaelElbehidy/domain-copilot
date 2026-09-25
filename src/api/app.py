from __future__ import annotations

from contextlib import AbstractAsyncContextManager
from typing import Callable

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
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
from api.routes import ask, auth, health, runs, sessions
from application.correlation import get_correlation_id
from config.api_settings import ApiSettings
from domain.errors.domain_errors import (
    InvalidCredentialsError,
    InvalidReviewEditError,
    InvalidRunTransitionError,
    InvalidTokenError,
    PermissionDeniedError,
    TamperedRunError,
    UnapprovedDispatchError,
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

    app.include_router(health.router)
    app.include_router(auth.router)
    app.include_router(ask.router)
    app.include_router(sessions.router)
    app.include_router(runs.router)

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
