from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime

from domain.entities.user import User
from domain.value_objects.role import Role


@dataclass(frozen=True)
class TokenClaims:
    user_id: str
    username: str
    role: Role
    expires_at: datetime


class PasswordHasher(ABC):
    @abstractmethod
    def hash(self, password: str) -> str: ...

    @abstractmethod
    def verify(self, password: str, stored_hash: str) -> bool: ...


class TokenService(ABC):
    @abstractmethod
    def issue(self, user: User) -> str: ...

    @abstractmethod
    def verify(self, token: str) -> TokenClaims:
        """Raises InvalidTokenError for anything that is not a valid,
        unexpired token issued by this service."""
        ...
