"""Applies migrations/*.sql to the configured Postgres.

Usage: python scripts/migrate.py
Reads POSTGRES_* from the environment (see .env.example).
"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import asyncpg  # noqa: E402

from infrastructure.persistence.migrations import apply_migrations  # noqa: E402


async def main() -> None:
    conn = await asyncpg.connect(
        user=os.environ.get("POSTGRES_USER", "domain_copilot"),
        password=os.environ.get("POSTGRES_PASSWORD", "domain_copilot_dev"),
        database=os.environ.get("POSTGRES_DB", "domain_copilot"),
        host=os.environ.get("POSTGRES_HOST", "localhost"),
        port=int(os.environ.get("POSTGRES_PORT", "5433")),
    )
    try:
        applied = await apply_migrations(conn)
    finally:
        await conn.close()
    print("applied: " + (", ".join(applied) if applied else "nothing (already up to date)"))


if __name__ == "__main__":
    asyncio.run(main())
