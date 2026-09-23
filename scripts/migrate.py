"""Applies migrations/*.sql in filename order, tracking what has already
run in a schema_migrations table -- deliberately simple (no ORM) since
this is the only place in the codebase that needs to touch raw SQL DDL.

Usage: python scripts/migrate.py
Reads POSTGRES_* from the environment (see .env.example).
"""

from __future__ import annotations

import asyncio
import os
from pathlib import Path

import asyncpg

MIGRATIONS_DIR = Path(__file__).resolve().parents[1] / "migrations"


async def main() -> None:
    conn = await asyncpg.connect(
        user=os.environ.get("POSTGRES_USER", "domain_copilot"),
        password=os.environ.get("POSTGRES_PASSWORD", "domain_copilot_dev"),
        database=os.environ.get("POSTGRES_DB", "domain_copilot"),
        host=os.environ.get("POSTGRES_HOST", "localhost"),
        port=int(os.environ.get("POSTGRES_PORT", "5432")),
    )
    try:
        await conn.execute(
            "CREATE TABLE IF NOT EXISTS schema_migrations "
            "(filename TEXT PRIMARY KEY, applied_at TIMESTAMPTZ NOT NULL DEFAULT now())"
        )
        applied = {
            row["filename"]
            for row in await conn.fetch("SELECT filename FROM schema_migrations")
        }

        for migration_file in sorted(MIGRATIONS_DIR.glob("*.sql")):
            if migration_file.name in applied:
                print(f"skip  {migration_file.name} (already applied)")
                continue
            sql = migration_file.read_text(encoding="utf-8")
            async with conn.transaction():
                await conn.execute(sql)
                await conn.execute(
                    "INSERT INTO schema_migrations (filename) VALUES ($1)",
                    migration_file.name,
                )
            print(f"apply {migration_file.name}")
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
