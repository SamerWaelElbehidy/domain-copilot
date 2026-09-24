from __future__ import annotations

from pathlib import Path

import asyncpg

MIGRATIONS_DIR = Path(__file__).resolve().parents[3] / "migrations"


async def apply_migrations(conn: asyncpg.Connection) -> list[str]:
    """Applies migrations/*.sql in filename order, recording each in
    schema_migrations. Returns the names applied this call."""
    await conn.execute(
        "CREATE TABLE IF NOT EXISTS schema_migrations "
        "(filename TEXT PRIMARY KEY, applied_at TIMESTAMPTZ NOT NULL DEFAULT now())"
    )
    done = {row["filename"] for row in await conn.fetch("SELECT filename FROM schema_migrations")}
    applied: list[str] = []
    for migration_file in sorted(MIGRATIONS_DIR.glob("*.sql")):
        if migration_file.name in done:
            continue
        async with conn.transaction():
            await conn.execute(migration_file.read_text(encoding="utf-8"))
            await conn.execute(
                "INSERT INTO schema_migrations (filename) VALUES ($1)", migration_file.name
            )
        applied.append(migration_file.name)
    return applied
