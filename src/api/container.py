from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

from api.rate_limit import TokenBucketLimiter
from application.ports.security import PasswordHasher, TokenService
from application.ports.user_repository import UserRepository
from config.api_settings import ApiSettings


@dataclass
class Container:
    """Everything the routes need, built once at the composition root
    (`api/main.py`) or by a test. Routes depend on ports, never on
    Postgres, Qdrant or any LLM SDK."""

    settings: ApiSettings
    users: UserRepository
    hasher: PasswordHasher
    tokens: TokenService
    dummy_hash: str
    login_limiter: TokenBucketLimiter
    readiness_checks: dict[str, Callable[[], Awaitable[bool]]] = field(default_factory=dict)
