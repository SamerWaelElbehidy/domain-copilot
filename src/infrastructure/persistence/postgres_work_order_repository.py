from __future__ import annotations

import json
from datetime import UTC, datetime

import asyncpg

from application.ports.work_order_repository import WorkOrderRepository
from domain.entities.work_order import WorkOrder, WorkOrderStatus
from domain.value_objects.citation import Citation


def _aware(value: datetime | None) -> datetime | None:
    if value is not None and value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value


class PostgresWorkOrderRepository(WorkOrderRepository):
    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    async def save(self, work_order: WorkOrder) -> None:
        await self._pool.execute(
            """
            INSERT INTO work_orders
                (work_order_id, equipment_id, symptom_description, diagnostic_steps,
                 safety_checklist, citations, status, created_at, approved_by, approved_at)
            VALUES ($1, $2, $3, $4::jsonb, $5::jsonb, $6::jsonb, $7, $8, $9, $10)
            ON CONFLICT (work_order_id) DO UPDATE SET
                symptom_description = EXCLUDED.symptom_description,
                diagnostic_steps = EXCLUDED.diagnostic_steps,
                safety_checklist = EXCLUDED.safety_checklist,
                citations = EXCLUDED.citations,
                status = EXCLUDED.status,
                approved_by = EXCLUDED.approved_by,
                approved_at = EXCLUDED.approved_at
            """,
            work_order.work_order_id,
            work_order.equipment_id,
            work_order.symptom_description,
            json.dumps(work_order.diagnostic_steps),
            json.dumps(work_order.safety_checklist),
            json.dumps([c.__dict__ for c in work_order.citations]),
            work_order.status.value,
            _aware(work_order.created_at),
            work_order.approved_by,
            _aware(work_order.approved_at),
        )

    async def get(self, work_order_id: str) -> WorkOrder | None:
        row = await self._pool.fetchrow(
            "SELECT * FROM work_orders WHERE work_order_id = $1", work_order_id
        )
        if row is None:
            return None
        return WorkOrder(
            work_order_id=row["work_order_id"],
            equipment_id=row["equipment_id"],
            symptom_description=row["symptom_description"],
            diagnostic_steps=json.loads(row["diagnostic_steps"]),
            safety_checklist=json.loads(row["safety_checklist"]),
            citations=[Citation(**c) for c in json.loads(row["citations"])],
            created_at=row["created_at"],
            status=WorkOrderStatus(row["status"]),
            approved_by=row["approved_by"],
            approved_at=row["approved_at"],
        )
