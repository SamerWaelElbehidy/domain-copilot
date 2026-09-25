from __future__ import annotations

import json
import logging
import time
from typing import Any

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from api.rate_limit import TokenBucketLimiter
from application.correlation import (
    accept_or_create,
    get_correlation_id,
    reset_correlation_id,
    set_correlation_id,
)

access_log = logging.getLogger("api.access")
error_log = logging.getLogger("api.error")

_DOC_PATHS = ("/docs", "/redoc")
_STRICT_CSP = "default-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"
# Swagger UI loads its script from a CDN and runs inline, so the interactive
# docs get a looser policy. Every other path keeps the strict one.
_DOCS_CSP = (
    "default-src 'self'; script-src 'self' https://cdn.jsdelivr.net 'unsafe-inline'; "
    "style-src 'self' https://cdn.jsdelivr.net 'unsafe-inline'; img-src 'self' data: "
    "https://fastapi.tiangolo.com; frame-ancestors 'none'"
)


def _header(scope: Scope, name: bytes) -> str | None:
    for key, value in scope.get("headers", []):
        if key == name:
            return value.decode("latin-1")
    return None


async def _json_response(send: Send, status: int, body: dict[str, Any], extra=None) -> None:
    payload = json.dumps(body).encode()
    headers = [
        (b"content-type", b"application/json"),
        (b"content-length", str(len(payload)).encode()),
    ]
    headers += extra or []
    await send({"type": "http.response.start", "status": status, "headers": headers})
    await send({"type": "http.response.body", "body": payload})


class CorrelationIdMiddleware:
    """Sets the correlation id for the request (honouring a safe caller
    supplied X-Request-ID), echoes it, and writes one access-log line that
    never includes the query string or credentials."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        request_id = accept_or_create(_header(scope, b"x-request-id"))
        reset = set_correlation_id(request_id)
        started = time.perf_counter()
        status_holder = {"status": 500}

        async def send_with_id(message: Message) -> None:
            if message["type"] == "http.response.start":
                status_holder["status"] = message["status"]
                message.setdefault("headers", []).append((b"x-request-id", request_id.encode()))
            await send(message)

        try:
            await self.app(scope, receive, send_with_id)
        finally:
            access_log.info(
                "%s %s -> %s in %.1fms",
                scope["method"], scope["path"], status_holder["status"],
                (time.perf_counter() - started) * 1000,
            )
            reset_correlation_id(reset)


class SecurityHeadersMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        path = scope["path"]
        csp = _DOCS_CSP if path.startswith(_DOC_PATHS) else _STRICT_CSP

        async def send_with_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = message.setdefault("headers", [])
                headers += [
                    (b"x-content-type-options", b"nosniff"),
                    (b"x-frame-options", b"DENY"),
                    (b"referrer-policy", b"no-referrer"),
                    (b"permissions-policy", b"camera=(), microphone=(), geolocation=()"),
                    (b"content-security-policy", csp.encode()),
                ]
                if not path.startswith(("/ui", *_DOC_PATHS, "/openapi.json")):
                    headers.append((b"cache-control", b"no-store"))
            await send(message)

        await self.app(scope, receive, send_with_headers)


class BodySizeLimitMiddleware:
    """Rejects oversized bodies (OWASP LLM: unbounded consumption). The
    declared Content-Length is checked up front and the bytes actually
    received are counted, so a client cannot lie about the size."""

    def __init__(self, app: ASGIApp, max_bytes: int, upload_max_bytes: int,
                 upload_prefixes: tuple[str, ...] = ("/documents",)) -> None:
        self.app = app
        self._max = max_bytes
        self._upload_max = upload_max_bytes
        self._upload_prefixes = upload_prefixes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        limit = self._upload_max if scope["path"].startswith(self._upload_prefixes) else self._max
        declared = _header(scope, b"content-length")
        if declared is not None and declared.isdigit() and int(declared) > limit:
            await _json_response(send, 413, {"detail": "request body too large"})
            return
        received = 0

        async def counting_receive() -> Message:
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > limit:
                    raise _BodyTooLarge()
            return message

        try:
            await self.app(scope, counting_receive, send)
        except _BodyTooLarge:
            await _json_response(send, 413, {"detail": "request body too large"})


class _BodyTooLarge(Exception):
    pass


class RateLimitMiddleware:
    """Coarse per-client-address limit for every request. Authenticated
    routes and login add their own tighter limits on top."""

    def __init__(self, app: ASGIApp, limiter: TokenBucketLimiter) -> None:
        self.app = app
        self._limiter = limiter

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        client = scope.get("client")
        key = client[0] if client else "unknown"
        if not self._limiter.allow(f"ip:{key}"):
            await _json_response(
                send, 429, {"detail": "rate limit exceeded"},
                [(b"retry-after", str(self._limiter.retry_after_seconds()).encode())],
            )
            return
        await self.app(scope, receive, send)


class ErrorBoundaryMiddleware:
    """Innermost catch-all: an unexpected exception becomes a generic 500
    carrying only the request id. Details go to the server log, never to
    the client (OWASP: security misconfiguration, information leakage)."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        started = False

        async def tracking_send(message: Message) -> None:
            nonlocal started
            if message["type"] == "http.response.start":
                started = True
            await send(message)

        try:
            await self.app(scope, receive, tracking_send)
        except _BodyTooLarge:
            raise
        except Exception:
            error_log.exception("unhandled error on %s %s", scope["method"], scope["path"])
            if not started:
                await _json_response(
                    send, 500, {"detail": "internal error", "request_id": get_correlation_id()}
                )
