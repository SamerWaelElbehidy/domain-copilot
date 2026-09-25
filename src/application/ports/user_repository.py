from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

from domain.entities.user import User


@dataclass(frozen=True)
class UserRecord:
    user: User
    password_hash: str


class UserRepository(ABC):
    @abstractmethod
    async def get_by_username(self, username: str) -> UserRecord | None: ...

    @abstractmethod
    async def get_by_id(self, user_id: str) -> User | None: ...

    @abstractmethod
    async def create(self, user: User, password_hash: str) -> None: ...
