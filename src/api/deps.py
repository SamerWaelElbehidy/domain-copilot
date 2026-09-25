from __future__ import annotations

import logging

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from api.container import Container
from domain.entities.user import User
from domain.errors.domain_errors import InvalidTokenError, PermissionDeniedError
from domain.value_objects.role import Permission, has_permission

_bearer = HTTPBearer(auto_error=False)
security_log = logging.getLogger("api.security")


def get_container(request: Request) -> Container:
    return request.app.state.container


async def current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    container: Container = Depends(get_container),
) -> User:
    """Authenticates the bearer token, then reloads the user so a disabled
    account or a changed role takes effect immediately instead of when the
    token expires."""
    if credentials is None:
        raise InvalidTokenError("missing bearer token")
    claims = container.tokens.verify(credentials.credentials)
    user = await container.users.get_by_id(claims.user_id)
    if user is None or user.disabled:
        raise InvalidTokenError("account not available")
    return user


def require(permission: Permission):
    """Server-side authorization (FR-8): the check runs on every request from
    the user's stored role. Hiding a button in the UI is never the control."""

    async def dependency(user: User = Depends(current_user)) -> User:
        if not has_permission(user.role, permission):
            security_log.warning(
                "permission denied user=%s role=%s permission=%s",
                user.username, user.role.value, permission.value,
            )
            raise PermissionDeniedError(f"role '{user.role.value}' may not {permission.value}")
        return user

    return dependency
