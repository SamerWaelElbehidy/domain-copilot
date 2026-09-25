from __future__ import annotations

from application.ports.security import PasswordHasher
from application.ports.user_repository import UserRepository
from domain.entities.user import User
from domain.errors.domain_errors import InvalidCredentialsError

# Verified against when the username does not exist, so the response time
# does not reveal which usernames are real (OWASP: user enumeration).
_DUMMY_HASH_PASSWORD = "not-a-real-password"


async def authenticate_user(
    *,
    users: UserRepository,
    hasher: PasswordHasher,
    username: str,
    password: str,
    dummy_hash: str,
) -> User:
    record = await users.get_by_username(username)
    if record is None:
        hasher.verify(password, dummy_hash)
        raise InvalidCredentialsError("invalid username or password")
    if not hasher.verify(password, record.password_hash) or record.user.disabled:
        raise InvalidCredentialsError("invalid username or password")
    return record.user


def make_dummy_hash(hasher: PasswordHasher) -> str:
    return hasher.hash(_DUMMY_HASH_PASSWORD)
