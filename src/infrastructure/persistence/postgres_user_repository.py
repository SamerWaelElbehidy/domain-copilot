from __future__ import annotations

import asyncpg

from application.ports.user_repository import UserRecord, UserRepository
from domain.entities.user import User
from domain.value_objects.role import Role


class PostgresUserRepository(UserRepository):
    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    async def get_by_username(self, username: str) -> UserRecord | None:
        row = await self._pool.fetchrow(
            "SELECT user_id, username, role, disabled, password_hash "
            "FROM users WHERE username = $1",
            username,
        )
        return None if row is None else UserRecord(_to_user(row), row["password_hash"])

    async def get_by_id(self, user_id: str) -> User | None:
        row = await self._pool.fetchrow(
            "SELECT user_id, username, role, disabled FROM users WHERE user_id = $1", user_id
        )
        return None if row is None else _to_user(row)

    async def create(self, user: User, password_hash: str) -> None:
        await self._pool.execute(
            """
            INSERT INTO users (user_id, username, role, disabled, password_hash)
            VALUES ($1, $2, $3, $4, $5)
            ON CONFLICT (username) DO NOTHING
            """,
            user.user_id,
            user.username,
            user.role.value,
            user.disabled,
            password_hash,
        )


def _to_user(row: asyncpg.Record) -> User:
    return User(
        user_id=row["user_id"],
        username=row["username"],
        role=Role(row["role"]),
        disabled=row["disabled"],
    )
