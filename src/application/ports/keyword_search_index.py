from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from application.ports.vector_store import ScoredChunk
from domain.entities.chunk import Chunk


class KeywordSearchIndex(ABC):
    """Lexical search, fused with VectorStore results via Reciprocal Rank
    Fusion to form FR-2's hybrid retrieval (ADR-0004)."""

    @abstractmethod
    async def index(self, chunks: list[Chunk]) -> None: ...

    @abstractmethod
    async def search(
        self,
        query: str,
        top_k: int,
        filters: dict[str, Any] | None = None,
    ) -> list[ScoredChunk]: ...

    @abstractmethod
    async def delete_by_document(self, document_id: str) -> None: ...
