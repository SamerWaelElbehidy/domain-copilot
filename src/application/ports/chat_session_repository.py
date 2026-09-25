from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass(frozen=True)
class ChatSession:
    session_id: str
    user_id: str
    title: str
    created_at: datetime


@dataclass(frozen=True)
class ChatMessage:
    role: str  # "user" | "assistant"
    content: str
    status: str
    created_at: datetime
    citations: list[dict[str, Any]] = field(default_factory=list)
    detail: str | None = None


class ChatSessionRepository(ABC):
    @abstractmethod
    async def create_session(self, user_id: str, title: str) -> ChatSession: ...

    @abstractmethod
    async def add_message(self, session_id: str, message: ChatMessage) -> None: ...

    @abstractmethod
    async def list_sessions(self, user_id: str) -> list[ChatSession]: ...

    @abstractmethod
    async def get_session(
        self, user_id: str, session_id: str
    ) -> tuple[ChatSession, list[ChatMessage]] | None:
        """Returns None when the session does not exist OR belongs to someone
        else, so a caller cannot tell the two apart (object-ownership check)."""
        ...

    @abstractmethod
    async def owns(self, user_id: str, session_id: str) -> bool: ...
