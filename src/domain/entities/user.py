from dataclasses import dataclass

from domain.value_objects.role import Role


@dataclass(frozen=True)
class User:
    user_id: str
    username: str
    role: Role
    disabled: bool = False
