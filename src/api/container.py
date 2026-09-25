from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

from api.rate_limit import TokenBucketLimiter
from api.run_manager import RunManager
from application.ports.chat_session_repository import ChatSessionRepository
from application.ports.llm_call_repository import LLMCallRepository
from application.ports.run_repository import RunRepository
from application.ports.security import PasswordHasher, TokenService
from application.ports.user_repository import UserRepository
from application.use_cases.answer_question import GroundedAnswerer
from application.use_cases.orchestrator import CopilotOrchestrator
from config.api_settings import ApiSettings


@dataclass
class Container:
    """Everything the routes need, built once at the composition root
    (`api/main.py`) or by a test. Routes depend on ports and use cases,
    never on Postgres, Qdrant or any LLM SDK."""

    settings: ApiSettings
    users: UserRepository
    hasher: PasswordHasher
    tokens: TokenService
    dummy_hash: str
    login_limiter: TokenBucketLimiter
    readiness_checks: dict[str, Callable[[], Awaitable[bool]]] = field(default_factory=dict)
    answerer: GroundedAnswerer | None = None
    sessions: ChatSessionRepository | None = None
    llm_calls: LLMCallRepository | None = None
    ask_limiter: TokenBucketLimiter | None = None
    runs: RunRepository | None = None
    orchestrator: CopilotOrchestrator | None = None
    run_manager: RunManager | None = None
