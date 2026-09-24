from __future__ import annotations

import json
from datetime import UTC, datetime

import asyncpg

from application.ports.run_repository import RunRepository
from domain.entities.run import Run
from domain.value_objects.run_state import RunState
from domain.value_objects.run_step import RunStep


def _aware(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value


class PostgresRunRepository(RunRepository):
    """Persists the audit log (ADR-0006). Steps are append-only: existing
    (run_id, step_index) rows are never updated. `get` rebuilds the Run
    without re-validating hashes, so a tampered log is caught by
    Run.verify_chain() instead of being silently rejected on load."""

    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    async def save(self, run: Run) -> None:
        async with self._pool.acquire() as conn, conn.transaction():
            await conn.execute(
                """
                INSERT INTO runs (run_id, equipment_id, started_at, state)
                VALUES ($1, $2, $3, $4)
                ON CONFLICT (run_id) DO UPDATE SET
                    equipment_id = EXCLUDED.equipment_id, state = EXCLUDED.state
                """,
                run.run_id,
                run.equipment_id,
                _aware(run.started_at),
                run.state.value,
            )
            for step in run.steps:
                await conn.execute(
                    """
                    INSERT INTO run_steps
                        (run_id, step_index, name, agent_name, provider_used, input_snapshot,
                         output_snapshot, input_tokens, output_tokens, started_at, finished_at,
                         status, step_hash)
                    VALUES ($1, $2, $3, $4, $5, $6::jsonb, $7::jsonb, $8, $9, $10, $11, $12, $13)
                    ON CONFLICT (run_id, step_index) DO NOTHING
                    """,
                    run.run_id,
                    step.step_index,
                    step.name,
                    step.agent_name,
                    step.provider_used,
                    json.dumps(step.input_snapshot),
                    json.dumps(step.output_snapshot),
                    step.input_tokens,
                    step.output_tokens,
                    _aware(step.started_at),
                    _aware(step.finished_at),
                    step.status,
                    step.step_hash,
                )

    async def get(self, run_id: str) -> Run | None:
        row = await self._pool.fetchrow("SELECT * FROM runs WHERE run_id = $1", run_id)
        if row is None:
            return None
        step_rows = await self._pool.fetch(
            "SELECT * FROM run_steps WHERE run_id = $1 ORDER BY step_index", run_id
        )
        steps = [
            RunStep(
                step_index=r["step_index"],
                name=r["name"],
                agent_name=r["agent_name"],
                provider_used=r["provider_used"],
                input_snapshot=json.loads(r["input_snapshot"]),
                output_snapshot=json.loads(r["output_snapshot"]),
                input_tokens=r["input_tokens"],
                output_tokens=r["output_tokens"],
                started_at=r["started_at"],
                finished_at=r["finished_at"],
                status=r["status"],
                step_hash=r["step_hash"],
            )
            for r in step_rows
        ]
        return Run(
            run_id=row["run_id"],
            equipment_id=row["equipment_id"],
            started_at=row["started_at"],
            state=RunState(row["state"]),
            steps=steps,
        )
