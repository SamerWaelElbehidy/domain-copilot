from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from api.container import Container
from api.deps import current_user, get_container
from application.use_cases.authenticate_user import authenticate_user
from domain.entities.user import User

router = APIRouter(prefix="/auth", tags=["auth"])
security_log = logging.getLogger("api.security")


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=256)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in_seconds: int
    role: str


class MeResponse(BaseModel):
    user_id: str
    username: str
    role: str


@router.post("/login", response_model=TokenResponse)
async def login(
    body: LoginRequest, request: Request, container: Container = Depends(get_container)
) -> TokenResponse:
    client = request.client.host if request.client else "unknown"
    if not container.login_limiter.allow(f"login:{client}:{body.username.lower()}"):
        security_log.warning("login throttled user=%s ip=%s", body.username, client)
        raise HTTPException(status_code=429, detail="too many login attempts")
    try:
        user = await authenticate_user(
            users=container.users,
            hasher=container.hasher,
            username=body.username,
            password=body.password,
            dummy_hash=container.dummy_hash,
        )
    except Exception:
        security_log.warning("login failed user=%s ip=%s", body.username, client)
        raise
    security_log.info("login ok user=%s role=%s ip=%s", user.username, user.role.value, client)
    return TokenResponse(
        access_token=container.tokens.issue(user),
        expires_in_seconds=container.settings.jwt_ttl_minutes * 60,
        role=user.role.value,
    )


@router.get("/me", response_model=MeResponse)
async def me(user: User = Depends(current_user)) -> MeResponse:
    return MeResponse(user_id=user.user_id, username=user.username, role=user.role.value)
