from __future__ import annotations

import os

import asyncpg


async def create_pool() -> asyncpg.Pool:
    return await asyncpg.create_pool(
        user=os.environ.get("POSTGRES_USER", "domain_copilot"),
        password=os.environ.get("POSTGRES_PASSWORD", "domain_copilot_dev"),
        database=os.environ.get("POSTGRES_DB", "domain_copilot"),
        host=os.environ.get("POSTGRES_HOST", "localhost"),
        port=int(os.environ.get("POSTGRES_PORT", "5432")),
    )
