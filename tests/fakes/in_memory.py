from __future__ import annotations

import re
from typing import Any

from application.ports.document_repository import DocumentRepository
from application.ports.keyword_search_index import KeywordSearchIndex
from application.ports.run_repository import RunRepository
from application.ports.vector_store import ScoredChunk, VectorStore
from application.ports.work_order_repository import WorkOrderRepository
from domain.entities.chunk import Chunk
from domain.entities.equipment import Equipment
from domain.entities.manual_document import ManualDocument
from domain.entities.run import Run
from domain.entities.work_order import WorkOrder


def _matches(chunk: Chunk, filters: dict[str, Any] | None) -> bool:
    for key, wanted in (filters or {}).items():
        actual = chunk.section_type.value if key == "section_type" else getattr(chunk, key)
        if isinstance(wanted, (list, tuple, set)):
            if actual not in wanted:
                return False
        elif actual != wanted:
            return False
    return True


def _tokens(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", text.lower()))


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    norm = (sum(x * x for x in a) ** 0.5) * (sum(y * y for y in b) ** 0.5)
    return dot / norm if norm else 0.0


class InMemoryVectorStore(VectorStore):
    """Applies real metadata filters and cosine ranking over the fake
    bag-of-words embeddings -- good enough to test the scoping/safety
    logic, not to judge semantic quality (that is what the live evaluation
    harness is for)."""

    def __init__(self) -> None:
        self.chunks: dict[str, Chunk] = {}
        self.vectors: dict[str, list[float]] = {}

    async def upsert(self, chunks: list[Chunk], embeddings: list[list[float]]) -> None:
        for chunk, vector in zip(chunks, embeddings, strict=True):
            self.chunks[chunk.chunk_id] = chunk
            self.vectors[chunk.chunk_id] = vector

    async def search(
        self, query_embedding: list[float], top_k: int, filters: dict[str, Any] | None = None
    ) -> list[ScoredChunk]:
        scored = [
            ScoredChunk(chunk=c, score=_cosine(query_embedding, self.vectors[c.chunk_id]))
            for c in self.chunks.values()
            if _matches(c, filters)
        ]
        scored.sort(key=lambda s: (-s.score, s.chunk.document_id, s.chunk.order_index))
        return scored[:top_k]

    async def delete_by_document(self, document_id: str) -> None:
        self.chunks = {k: c for k, c in self.chunks.items() if c.document_id != document_id}
        self.vectors = {k: v for k, v in self.vectors.items() if k in self.chunks}


class InMemoryKeywordIndex(KeywordSearchIndex):
    def __init__(self) -> None:
        self.chunks: dict[str, Chunk] = {}

    async def index(self, chunks: list[Chunk]) -> None:
        for chunk in chunks:
            self.chunks[chunk.chunk_id] = chunk

    async def search(
        self, query: str, top_k: int, filters: dict[str, Any] | None = None
    ) -> list[ScoredChunk]:
        wanted = _tokens(query)
        scored = [
            ScoredChunk(chunk=c, score=float(len(wanted & _tokens(c.content))))
            for c in self.chunks.values()
            if _matches(c, filters)
        ]
        scored = [s for s in scored if s.score > 0]
        scored.sort(key=lambda s: (-s.score, s.chunk.chunk_id))
        return scored[:top_k]

    async def delete_by_document(self, document_id: str) -> None:
        self.chunks = {k: c for k, c in self.chunks.items() if c.document_id != document_id}


class InMemoryDocumentRepository(DocumentRepository):
    def __init__(self) -> None:
        self.equipment: dict[str, Equipment] = {}
        self.documents: dict[str, ManualDocument] = {}
        self.ingestion_status: dict[str, tuple[str, str | None]] = {}

    async def save_equipment(self, equipment: Equipment) -> None:
        self.equipment[equipment.equipment_id] = equipment

    async def get_equipment(self, equipment_id: str) -> Equipment | None:
        return self.equipment.get(equipment_id)

    async def save_document(self, document: ManualDocument) -> None:
        self.documents[document.document_id] = document

    async def get_document(self, document_id: str) -> ManualDocument | None:
        return self.documents.get(document_id)

    async def list_documents_for_equipment(self, equipment_id: str) -> list[ManualDocument]:
        return sorted(
            (d for d in self.documents.values() if d.equipment_id == equipment_id),
            key=lambda d: d.effective_date,
        )

    async def set_ingestion_status(
        self, document_id: str, status: str, error: str | None = None
    ) -> None:
        self.ingestion_status[document_id] = (status, error)

    async def list_current_document_ids(self, equipment_id: str | None = None) -> list[str]:
        return sorted(
            d.document_id
            for d in self.documents.values()
            if d.status == "current" and (equipment_id is None or d.equipment_id == equipment_id)
        )


class InMemoryWorkOrderRepository(WorkOrderRepository):
    def __init__(self) -> None:
        self.work_orders: dict[str, WorkOrder] = {}

    async def save(self, work_order: WorkOrder) -> None:
        self.work_orders[work_order.work_order_id] = work_order

    async def get(self, work_order_id: str) -> WorkOrder | None:
        return self.work_orders.get(work_order_id)


class InMemoryRunRepository(RunRepository):
    def __init__(self) -> None:
        self.runs: dict[str, Run] = {}

    async def save(self, run: Run) -> None:
        self.runs[run.run_id] = run

    async def get(self, run_id: str) -> Run | None:
        return self.runs.get(run_id)
