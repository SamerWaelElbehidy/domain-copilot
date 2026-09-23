from __future__ import annotations

from abc import ABC, abstractmethod

from domain.entities.equipment import Equipment
from domain.entities.manual_document import ManualDocument


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
