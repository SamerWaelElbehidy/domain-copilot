"""Creates the demo accounts (one per role). Demo data only: these are
synthetic users for the 5-minute demo path, never real people.

Usage: python scripts/seed_users.py
Passwords come from DEMO_PASSWORD (default below). Change it for anything
other than a local demo.
"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from domain.entities.user import User  # noqa: E402
from domain.value_objects.role import Role  # noqa: E402
from infrastructure.persistence.postgres_pool import create_pool  # noqa: E402
from infrastructure.persistence.postgres_user_repository import PostgresUserRepository  # noqa: E402
from infrastructure.security.password_hasher import ScryptPasswordHasher  # noqa: E402

DEMO_ACCOUNTS = [
    ("u-tech1", "technician1", Role.TECHNICIAN),
    ("u-tech2", "technician2", Role.TECHNICIAN),
    ("u-super1", "supervisor1", Role.SUPERVISOR),
    ("u-admin1", "admin1", Role.ADMIN),
]


async def main() -> None:
    password = os.environ.get("DEMO_PASSWORD", "demo-password-change-me")
    hasher = ScryptPasswordHasher()
    pool = await create_pool()
    try:
        users = PostgresUserRepository(pool)
        for user_id, username, role in DEMO_ACCOUNTS:
            await users.create(User(user_id, username, role), hasher.hash(password))
            print(f"ready: {username} ({role.value})")
    finally:
        await pool.close()
    print("\nDemo password is taken from DEMO_PASSWORD (see .env.example).")


if __name__ == "__main__":
    asyncio.run(main())
