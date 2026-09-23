from __future__ import annotations

from typing import Any

from application.ports.vector_store import ScoredChunk, VectorStore
from domain.entities.chunk import Chunk


class FakeVectorStore(VectorStore):
    """In-memory stand-in for tests. `configured_results` is returned by
    every `search()` call regardless of the query embedding -- tests
    control ranking by ordering that list themselves."""

    def __init__(self, configured_results: list[ScoredChunk] | None = None) -> None:
        self._configured_results = configured_results or []
        self.upserted: list[Chunk] = []

    async def upsert(self, chunks: list[Chunk], embeddings: list[list[float]]) -> None:
        self.upserted.extend(chunks)

    async def search(
        self,
        query_embedding: list[float],
        top_k: int,
        filters: dict[str, Any] | None = None,
    ) -> list[ScoredChunk]:
        return self._configured_results[:top_k]

    async def delete_by_document(self, document_id: str) -> None:
        self.upserted = [c for c in self.upserted if c.document_id != document_id]
