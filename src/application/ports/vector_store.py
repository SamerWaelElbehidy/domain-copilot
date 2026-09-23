from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

from domain.entities.chunk import Chunk


@dataclass(frozen=True)
class ScoredChunk:
    chunk: Chunk
    score: float


class VectorStore(ABC):
    """Dense-vector storage and metadata-filtered search. Hybrid fusion
    with KeywordSearchIndex (FR-2) is composed in the application layer,
    not baked in here, so the fusion method stays swappable independent
    of which vector store backs this port (ADR-0004)."""

    @abstractmethod
    async def upsert(self, chunks: list[Chunk], embeddings: list[list[float]]) -> None: ...

    @abstractmethod
    async def search(
        self,
        query_embedding: list[float],
        top_k: int,
        filters: dict[str, Any] | None = None,
    ) -> list[ScoredChunk]: ...

    @abstractmethod
    async def delete_by_document(self, document_id: str) -> None:
        """Re-ingesting a document clears its old chunks first (FR-1:
        idempotent re-ingestion)."""
        ...
