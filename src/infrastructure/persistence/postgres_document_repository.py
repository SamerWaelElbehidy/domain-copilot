from __future__ import annotations

import asyncpg

from application.ports.document_repository import DocumentRepository
from domain.entities.equipment import Equipment
from domain.entities.manual_document import ManualDocument


class PostgresDocumentRepository(DocumentRepository):
    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    async def save_equipment(self, equipment: Equipment) -> None:
        await self._pool.execute(
            """
            INSERT INTO equipment (equipment_id, name, model_number, category)
            VALUES ($1, $2, $3, $4)
            ON CONFLICT (equipment_id) DO UPDATE SET
                name = EXCLUDED.name,
                model_number = EXCLUDED.model_number,
                category = EXCLUDED.category
            """,
            equipment.equipment_id,
            equipment.name,
            equipment.model_number,
            equipment.category,
        )

    async def get_equipment(self, equipment_id: str) -> Equipment | None:
        row = await self._pool.fetchrow(
            "SELECT equipment_id, name, model_number, category "
            "FROM equipment WHERE equipment_id = $1",
            equipment_id,
        )
        return _row_to_equipment(row) if row else None

    async def save_document(self, document: ManualDocument) -> None:
        await self._pool.execute(
            """
            INSERT INTO manual_documents
                (document_id, equipment_id, revision, effective_date, title)
            VALUES ($1, $2, $3, $4, $5)
            ON CONFLICT (document_id) DO UPDATE SET
                revision = EXCLUDED.revision,
                effective_date = EXCLUDED.effective_date,
                title = EXCLUDED.title
            """,
            document.document_id,
            document.equipment_id,
            document.revision,
            document.effective_date,
            document.title,
        )

    async def get_document(self, document_id: str) -> ManualDocument | None:
        row = await self._pool.fetchrow(
            "SELECT document_id, equipment_id, revision, effective_date, title "
            "FROM manual_documents WHERE document_id = $1",
            document_id,
        )
        return _row_to_document(row) if row else None

    async def list_documents_for_equipment(self, equipment_id: str) -> list[ManualDocument]:
        rows = await self._pool.fetch(
            "SELECT document_id, equipment_id, revision, effective_date, title "
            "FROM manual_documents WHERE equipment_id = $1 ORDER BY effective_date",
            equipment_id,
        )
        return [_row_to_document(row) for row in rows]


def _row_to_equipment(row: asyncpg.Record) -> Equipment:
    return Equipment(
        equipment_id=row["equipment_id"],
        name=row["name"],
        model_number=row["model_number"],
        category=row["category"],
    )


def _row_to_document(row: asyncpg.Record) -> ManualDocument:
    return ManualDocument(
        document_id=row["document_id"],
        equipment_id=row["equipment_id"],
        revision=row["revision"],
        effective_date=row["effective_date"],
        title=row["title"],
    )
