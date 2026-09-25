"""Correlation ID for one request (FR-9). The API sets it on the way in; the
orchestrator, agents and the LLM-call recorder read it, so a single id links
a request to every step and model call it caused."""

from __future__ import annotations

import contextvars
import re
import uuid
from dataclasses import dataclass

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


@dataclass(frozen=True)
class UsageContext:
    """Who and what an LLM call is for, read by the call recorder so token
    and cost accounting is attributed without threading arguments through
    every layer."""

    user_id: str | None = None
    run_id: str | None = None
    purpose: str = "unspecified"


_usage_context: contextvars.ContextVar[UsageContext | None] = contextvars.ContextVar(
    "usage_context", default=None
)


def set_usage_context(context: UsageContext) -> contextvars.Token[UsageContext | None]:
    return _usage_context.set(context)


def get_usage_context() -> UsageContext:
    return _usage_context.get() or UsageContext()


def reset_usage_context(token: contextvars.Token[UsageContext | None]) -> None:
    _usage_context.reset(token)
