from __future__ import annotations

import uuid
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

import jwt

from application.ports.security import TokenClaims, TokenService
from domain.entities.user import User
from domain.errors.domain_errors import InvalidTokenError
from domain.value_objects.role import Role

_ISSUER = "domain-copilot"
_ALGORITHM = "HS256"


class JwtTokenService(TokenService):
    """HS256 access tokens. The accepted algorithm is pinned (never taken
    from the token header, which is what makes `alg: none` attacks work),
    and issuer and expiry are required."""

    def __init__(
        self,
        secret: str,
        ttl_minutes: int = 60,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        if len(secret) < 32:
            raise ValueError("JWT secret must be at least 32 characters")
        self._secret = secret
        self._ttl = timedelta(minutes=ttl_minutes)
        self._clock = clock

    def issue(self, user: User) -> str:
        now = self._clock()
        return jwt.encode(
            {
                "sub": user.user_id,
                "username": user.username,
                "role": user.role.value,
                "iss": _ISSUER,
                "iat": int(now.timestamp()),
                "exp": int((now + self._ttl).timestamp()),
                "jti": uuid.uuid4().hex,
            },
            self._secret,
            algorithm=_ALGORITHM,
        )

    def verify(self, token: str) -> TokenClaims:
        try:
            payload = jwt.decode(
                token,
                self._secret,
                algorithms=[_ALGORITHM],
                issuer=_ISSUER,
                options={"require": ["exp", "iss", "sub"], "verify_exp": False},
            )
            expires_at = datetime.fromtimestamp(payload["exp"], UTC)
            if expires_at <= self._clock():
                raise InvalidTokenError("token expired")
            return TokenClaims(
                user_id=payload["sub"],
                username=payload["username"],
                role=Role(payload["role"]),
                expires_at=expires_at,
            )
        except InvalidTokenError:
            raise
        except (jwt.PyJWTError, KeyError, ValueError) as exc:
            raise InvalidTokenError("invalid token") from exc
