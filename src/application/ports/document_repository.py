from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

from domain.entities.equipment import Equipment
from domain.entities.manual_document import ManualDocument


@dataclass(frozen=True)
class DocumentStatusRow:
    document: ManualDocument
    ingestion_status: str
    ingestion_error: str | None


class DocumentRepository(ABC):
    """Relational metadata store for equipment and manual documents --
    separate from vector storage so per-document ingestion status (FR-1)
    can be queried without touching the vector store."""

    @abstractmethod
    async def save_equipment(self, equipment: Equipment) -> None: ...

    @abstractmethod
    async def get_equipment(self, equipment_id: str) -> Equipment | None: ...

    @abstractmethod
    async def save_document(self, document: ManualDocument) -> None: ...

    @abstractmethod
    async def get_document(self, document_id: str) -> ManualDocument | None: ...

    @abstractmethod
    async def list_documents_for_equipment(self, equipment_id: str) -> list[ManualDocument]: ...

    @abstractmethod
    async def set_ingestion_status(
        self, document_id: str, status: str, error: str | None = None
    ) -> None:
        """FR-1: per-document ingestion status ('ingested' or 'failed') with
        the failure reason, queryable without touching the vector store."""
        ...

    @abstractmethod
    async def list_current_document_ids(self, equipment_id: str | None = None) -> list[str]:
        """Ids of non-superseded documents. Every agent retrieval is
        restricted to these, so stale revisions are never cited."""
        ...

    @abstractmethod
    async def list_equipment(self) -> list[Equipment]: ...

    @abstractmethod
    async def list_with_status(self) -> list[DocumentStatusRow]:
        """Every document with its ingestion status, newest effective date first."""
        ...
