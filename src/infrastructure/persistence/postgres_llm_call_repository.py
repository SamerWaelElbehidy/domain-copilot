from __future__ import annotations

from datetime import datetime

import asyncpg

from application.ports.llm_call_repository import LLMCall, LLMCallRepository, UsageRow


class PostgresLLMCallRepository(LLMCallRepository):
    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    async def record(self, call: LLMCall) -> None:
        await self._pool.execute(
            """
            INSERT INTO llm_calls
                (correlation_id, user_id, run_id, purpose, provider, model, operation,
                 input_tokens, output_tokens, cost_usd, latency_ms, status, created_at)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13)
            """,
            call.correlation_id,
            call.user_id,
            call.run_id,
            call.purpose,
            call.provider,
            call.model,
            call.operation,
            call.input_tokens,
            call.output_tokens,
            call.cost_usd,
            call.latency_ms,
            call.status,
            call.created_at,
        )

    async def usage_by_user(self, since: datetime) -> list[UsageRow]:
        rows = await self._pool.fetch(
            """
            SELECT user_id, count(*) AS calls, sum(input_tokens) AS tin,
                   sum(output_tokens) AS tout, sum(cost_usd) AS cost
            FROM llm_calls WHERE created_at >= $1
            GROUP BY user_id ORDER BY tin DESC NULLS LAST
            """,
            since,
        )
        return [
            UsageRow(r["user_id"], r["calls"], int(r["tin"] or 0), int(r["tout"] or 0),
                     float(r["cost"] or 0))
            for r in rows
        ]

    async def calls_for_correlation(self, correlation_id: str) -> list[LLMCall]:
        rows = await self._pool.fetch(
            "SELECT * FROM llm_calls WHERE correlation_id = $1 ORDER BY call_id", correlation_id
        )
        return [_to_call(r) for r in rows]

    async def calls_for_run(self, run_id: str) -> list[LLMCall]:
        rows = await self._pool.fetch(
            "SELECT * FROM llm_calls WHERE run_id = $1 ORDER BY call_id", run_id
        )
        return [_to_call(r) for r in rows]


def _to_call(r: asyncpg.Record) -> LLMCall:
    return LLMCall(
        correlation_id=r["correlation_id"], user_id=r["user_id"], run_id=r["run_id"],
        purpose=r["purpose"], provider=r["provider"], model=r["model"],
        operation=r["operation"], input_tokens=r["input_tokens"],
        output_tokens=r["output_tokens"], cost_usd=float(r["cost_usd"]),
        latency_ms=r["latency_ms"], status=r["status"], created_at=r["created_at"],
    )
