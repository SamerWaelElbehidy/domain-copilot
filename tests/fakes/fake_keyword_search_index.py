from __future__ import annotations

from typing import Any

from application.ports.keyword_search_index import KeywordSearchIndex
from application.ports.vector_store import ScoredChunk
from domain.entities.chunk import Chunk


class FakeKeywordSearchIndex(KeywordSearchIndex):
    """In-memory stand-in for tests, mirroring FakeVectorStore."""

    def __init__(self, configured_results: list[ScoredChunk] | None = None) -> None:
        self._configured_results = configured_results or []
        self.indexed: list[Chunk] = []

    async def index(self, chunks: list[Chunk]) -> None:
        self.indexed.extend(chunks)

    async def search(
        self,
        query: str,
        top_k: int,
        filters: dict[str, Any] | None = None,
    ) -> list[ScoredChunk]:
        return self._configured_results[:top_k]

    async def delete_by_document(self, document_id: str) -> None:
        self.indexed = [c for c in self.indexed if c.document_id != document_id]
