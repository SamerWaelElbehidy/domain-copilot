from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime

import asyncpg

from application.ports.chat_session_repository import (
    ChatMessage,
    ChatSession,
    ChatSessionRepository,
)


def _session(row: asyncpg.Record) -> ChatSession:
    return ChatSession(row["session_id"], row["user_id"], row["title"], row["created_at"])


class PostgresChatSessionRepository(ChatSessionRepository):
    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    async def create_session(self, user_id: str, title: str) -> ChatSession:
        session = ChatSession(f"s-{uuid.uuid4().hex[:16]}", user_id, title[:120], datetime.now(UTC))
        await self._pool.execute(
            "INSERT INTO chat_sessions (session_id, user_id, title, created_at) "
            "VALUES ($1, $2, $3, $4)",
            session.session_id, session.user_id, session.title, session.created_at,
        )
        return session

    async def add_message(self, session_id: str, message: ChatMessage) -> None:
        await self._pool.execute(
            "INSERT INTO chat_messages "
            "(session_id, role, content, status, citations, detail, created_at) "
            "VALUES ($1, $2, $3, $4, $5::jsonb, $6, $7)",
            session_id, message.role, message.content, message.status,
            json.dumps(message.citations), message.detail, message.created_at,
        )

    async def list_sessions(self, user_id: str) -> list[ChatSession]:
        rows = await self._pool.fetch(
            "SELECT * FROM chat_sessions WHERE user_id = $1 ORDER BY created_at DESC LIMIT 100",
            user_id,
        )
        return [_session(r) for r in rows]

    async def get_session(
        self, user_id: str, session_id: str
    ) -> tuple[ChatSession, list[ChatMessage]] | None:
        row = await self._pool.fetchrow(
            "SELECT * FROM chat_sessions WHERE session_id = $1 AND user_id = $2",
            session_id, user_id,
        )
        if row is None:
            return None
        messages = await self._pool.fetch(
            "SELECT * FROM chat_messages WHERE session_id = $1 ORDER BY message_id", session_id
        )
        return _session(row), [
            ChatMessage(
                role=m["role"], content=m["content"], status=m["status"],
                created_at=m["created_at"], citations=json.loads(m["citations"]),
                detail=m["detail"],
            )
            for m in messages
        ]

    async def owns(self, user_id: str, session_id: str) -> bool:
        return bool(
            await self._pool.fetchval(
                "SELECT 1 FROM chat_sessions WHERE session_id = $1 AND user_id = $2",
                session_id, user_id,
            )
        )
