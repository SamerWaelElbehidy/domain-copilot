from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from api.container import Container
from api.deps import current_user, get_container, require
from domain.entities.user import User
from domain.value_objects.role import Permission

router = APIRouter(tags=["history"])
_can_view_usage = require(Permission.VIEW_USAGE)


class SessionSummary(BaseModel):
    session_id: str
    title: str
    created_at: datetime


class MessageOut(BaseModel):
    role: str
    content: str
    status: str
    created_at: datetime
    citations: list[dict[str, Any]]
    detail: str | None


class SessionDetail(SessionSummary):
    messages: list[MessageOut]


class UsageOut(BaseModel):
    user_id: str | None
    calls: int
    input_tokens: int
    output_tokens: int
    cost_usd: float


@router.get("/sessions", response_model=list[SessionSummary])
async def list_sessions(
    user: User = Depends(current_user), container: Container = Depends(get_container)
) -> list[SessionSummary]:
    """Persistent session history (FR-7). A user only ever sees their own."""
    assert container.sessions is not None
    return [
        SessionSummary(session_id=s.session_id, title=s.title, created_at=s.created_at)
        for s in await container.sessions.list_sessions(user.user_id)
    ]


@router.get("/sessions/{session_id}", response_model=SessionDetail)
async def get_session(
    session_id: str,
    user: User = Depends(current_user),
    container: Container = Depends(get_container),
) -> SessionDetail:
    assert container.sessions is not None
    found = await container.sessions.get_session(user.user_id, session_id)
    if found is None:
        raise HTTPException(status_code=404, detail="session not found")
    session, messages = found
    return SessionDetail(
        session_id=session.session_id, title=session.title, created_at=session.created_at,
        messages=[MessageOut(**m.__dict__) for m in messages],
    )


@router.get("/usage", response_model=list[UsageOut])
async def usage(
    days: int = Query(default=7, ge=1, le=90),
    _: User = Depends(_can_view_usage),
    container: Container = Depends(get_container),
) -> list[UsageOut]:
    """Per-user token and cost accounting, persisted and queryable (FR-9)."""
    assert container.llm_calls is not None
    since = datetime.now(UTC) - timedelta(days=days)
    return [UsageOut(**row.__dict__) for row in await container.llm_calls.usage_by_user(since)]
