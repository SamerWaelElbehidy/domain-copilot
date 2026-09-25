from __future__ import annotations

import asyncpg

from application.ports.document_repository import DocumentRepository, DocumentStatusRow
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
                (document_id, equipment_id, revision, effective_date, title, doc_type, status)
            VALUES ($1, $2, $3, $4, $5, $6, $7)
            ON CONFLICT (document_id) DO UPDATE SET
                revision = EXCLUDED.revision,
                effective_date = EXCLUDED.effective_date,
                title = EXCLUDED.title,
                doc_type = EXCLUDED.doc_type,
                status = EXCLUDED.status
            """,
            document.document_id,
            document.equipment_id,
            document.revision,
            document.effective_date,
            document.title,
            document.doc_type,
            document.status,
        )

    async def get_document(self, document_id: str) -> ManualDocument | None:
        row = await self._pool.fetchrow(
            "SELECT document_id, equipment_id, revision, effective_date, title, doc_type, status "
            "FROM manual_documents WHERE document_id = $1",
            document_id,
        )
        return _row_to_document(row) if row else None

    async def list_documents_for_equipment(self, equipment_id: str) -> list[ManualDocument]:
        rows = await self._pool.fetch(
            "SELECT document_id, equipment_id, revision, effective_date, title, doc_type, status "
            "FROM manual_documents WHERE equipment_id = $1 ORDER BY effective_date",
            equipment_id,
        )
        return [_row_to_document(row) for row in rows]

    async def set_ingestion_status(
        self, document_id: str, status: str, error: str | None = None
    ) -> None:
        await self._pool.execute(
            "UPDATE manual_documents SET ingestion_status = $2, ingestion_error = $3, "
            "ingested_at = CASE WHEN $2 = 'ingested' THEN now() ELSE ingested_at END "
            "WHERE document_id = $1",
            document_id,
            status,
            error,
        )

    async def list_with_status(self) -> list[DocumentStatusRow]:
        rows = await self._pool.fetch(
            "SELECT document_id, equipment_id, revision, effective_date, title, doc_type, status, "
            "ingestion_status, ingestion_error FROM manual_documents "
            "ORDER BY effective_date DESC, document_id"
        )
        return [
            DocumentStatusRow(
                _row_to_document(r), r["ingestion_status"], r["ingestion_error"]
            )
            for r in rows
        ]

    async def list_current_document_ids(self, equipment_id: str | None = None) -> list[str]:
        if equipment_id is None:
            rows = await self._pool.fetch(
                "SELECT document_id FROM manual_documents WHERE status = 'current' "
                "ORDER BY document_id"
            )
        else:
            rows = await self._pool.fetch(
                "SELECT document_id FROM manual_documents "
                "WHERE status = 'current' AND equipment_id = $1 ORDER BY document_id",
                equipment_id,
            )
        return [row["document_id"] for row in rows]


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
        doc_type=row["doc_type"],
        status=row["status"],
    )
