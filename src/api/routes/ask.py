from __future__ import annotations

import json
import re
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from api.container import Container
from api.deps import get_container, require
from application.correlation import (
    UsageContext,
    get_correlation_id,
    reset_usage_context,
    set_usage_context,
)
from application.ports.chat_session_repository import ChatMessage
from domain.entities.user import User
from domain.value_objects.role import Permission

router = APIRouter(tags=["ask"])
_can_ask = require(Permission.ASK)
_CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


class AskRequest(BaseModel):
    question: str = Field(min_length=3, max_length=1000)
    equipment_id: str | None = Field(default=None, max_length=64)
    session_id: str | None = Field(default=None, max_length=64)


class AskResponse(BaseModel):
    session_id: str
    correlation_id: str
    status: str
    answer: str
    reason: str | None
    detail: str | None
    citations: list[dict[str, Any]]


def _clean(question: str) -> str:
    return _CONTROL_CHARS.sub("", question).strip()


async def _prepare(body: AskRequest, user: User, container: Container) -> tuple[str, str]:
    if container.answerer is None or container.sessions is None:
        raise HTTPException(status_code=503, detail="answering is not configured")
    if container.ask_limiter is not None and not container.ask_limiter.allow(f"ask:{user.user_id}"):
        raise HTTPException(status_code=429, detail="too many questions, slow down")
    question = _clean(body.question)
    if len(question) < 3:
        raise HTTPException(status_code=422, detail="question is empty after cleaning")

    if body.session_id is not None:
        # 404 for someone else's session, exactly like a missing one.
        if not await container.sessions.owns(user.user_id, body.session_id):
            raise HTTPException(status_code=404, detail="session not found")
        session_id = body.session_id
    else:
        session_id = (await container.sessions.create_session(user.user_id, question)).session_id
    await container.sessions.add_message(
        session_id, ChatMessage("user", question, "asked", datetime.now(UTC))
    )
    return session_id, question


async def _store_answer(container: Container, session_id: str, answer: dict[str, Any]) -> None:
    assert container.sessions is not None
    await container.sessions.add_message(
        session_id,
        ChatMessage(
            role="assistant",
            content=answer["answer"],
            status=answer["status"],
            created_at=datetime.now(UTC),
            citations=answer["citations"],
            detail=answer.get("detail") or answer.get("reason"),
        ),
    )


@router.post("/ask", response_model=AskResponse)
async def ask(
    body: AskRequest,
    user: User = Depends(_can_ask),
    container: Container = Depends(get_container),
) -> AskResponse:
    """Grounded answer with citations. Refusal ("not enough information") is a
    normal, required outcome and is returned with its reason."""
    session_id, question = await _prepare(body, user, container)
    token = set_usage_context(UsageContext(user_id=user.user_id, purpose="ask"))
    try:
        result = await container.answerer.answer(question, body.equipment_id)  # type: ignore[union-attr]
    finally:
        reset_usage_context(token)
    payload = result.as_dict()
    await _store_answer(container, session_id, payload)
    return AskResponse(
        session_id=session_id, correlation_id=get_correlation_id(), status=payload["status"],
        answer=payload["answer"], reason=payload["reason"], detail=payload["detail"],
        citations=payload["citations"],
    )


def _sse(event: dict[str, Any]) -> bytes:
    return f"event: {event['type']}\ndata: {json.dumps(event)}\n\n".encode()


@router.post("/ask/stream")
async def ask_stream(
    body: AskRequest,
    user: User = Depends(_can_ask),
    container: Container = Depends(get_container),
) -> StreamingResponse:
    """Server-sent events: `session`, `retrieval`, `token`*, `answer`. Tokens
    are provisional model output; only the final `answer` event is validated.
    If the client disconnects, the generator is cancelled, the provider
    stream is closed, and the model stops generating."""
    session_id, question = await _prepare(body, user, container)
    correlation_id = get_correlation_id()

    async def events() -> AsyncIterator[bytes]:
        token = set_usage_context(UsageContext(user_id=user.user_id, purpose="ask"))
        yield _sse({"type": "session", "session_id": session_id,
                    "correlation_id": correlation_id})
        stream = container.answerer.answer_stream(question, body.equipment_id)  # type: ignore[union-attr]
        try:
            async for event in stream:
                if event["type"] == "answer":
                    await _store_answer(container, session_id, event["answer"])
                yield _sse(event)
        finally:
            await stream.aclose()
            reset_usage_context(token)

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"},
    )
