"""Correlation ID for one request (FR-9). The API sets it on the way in; the
orchestrator, agents and the LLM-call recorder read it, so a single id links
a request to every step and model call it caused."""

from __future__ import annotations

import contextvars
import re
import uuid

_correlation_id: contextvars.ContextVar[str] = contextvars.ContextVar(
    "correlation_id", default="-"
)
_VALID = re.compile(r"^[A-Za-z0-9._-]{8,64}$")


def new_correlation_id() -> str:
    return uuid.uuid4().hex


def accept_or_create(candidate: str | None) -> str:
    """A caller-supplied id is honoured only if it is a safe token, so it
    cannot smuggle log-injection characters."""
    return candidate if candidate and _VALID.match(candidate) else new_correlation_id()


def set_correlation_id(value: str) -> contextvars.Token[str]:
    return _correlation_id.set(value)


def get_correlation_id() -> str:
    return _correlation_id.get()


def reset_correlation_id(token: contextvars.Token[str]) -> None:
    _correlation_id.reset(token)
