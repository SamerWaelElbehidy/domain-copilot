from __future__ import annotations

from typing import Any

import asyncpg

from application.ports.keyword_search_index import KeywordSearchIndex
from application.ports.vector_store import ScoredChunk
from domain.entities.chunk import Chunk
from domain.value_objects.section_type import SectionType

# Filter keys are interpolated as column names (values stay parameterized
# below) -- allowlisted to close the injection path OWASP Web Top 10
# flags, even though today's only caller passes fixed internal strings.
_ALLOWED_FILTER_COLUMNS = {"document_id", "equipment_id", "manual_revision", "section_type"}


class PostgresKeywordSearchIndex(KeywordSearchIndex):
    """Lexical half of hybrid retrieval (ADR-0004), via Postgres full-text
    search (chunks_fts, migration 0002)."""

    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    async def index(self, chunks: list[Chunk]) -> None:
        if not chunks:
            return
        await self._pool.executemany(
            """
            INSERT INTO chunks_fts
                (chunk_id, document_id, equipment_id, manual_revision,
                 section_type, section_title, content, order_index, source_ref)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
            ON CONFLICT (chunk_id) DO UPDATE SET
                content = EXCLUDED.content,
                section_title = EXCLUDED.section_title,
                order_index = EXCLUDED.order_index,
                source_ref = EXCLUDED.source_ref
            """,
            [
                (
                    c.chunk_id,
                    c.document_id,
                    c.equipment_id,
                    c.manual_revision,
                    c.section_type.value,
                    c.section_title,
                    c.content,
                    c.order_index,
                    c.source_ref,
                )
                for c in chunks
            ],
        )

    async def search(
        self,
        query: str,
        top_k: int,
        filters: dict[str, Any] | None = None,
    ) -> list[ScoredChunk]:
        where_clauses = ["search_vector @@ plainto_tsquery('english', $1)"]
        params: list[Any] = [query]

        for key, value in (filters or {}).items():
            if key not in _ALLOWED_FILTER_COLUMNS:
                raise ValueError(f"Unsupported filter column: {key}")
            params.append(value)
            where_clauses.append(f"{key} = ${len(params)}")

        params.append(top_k)
        sql = f"""
            SELECT chunk_id, document_id, equipment_id, manual_revision,
                   section_type, section_title, content, order_index, source_ref,
                   ts_rank(search_vector, plainto_tsquery('english', $1)) AS score
            FROM chunks_fts
            WHERE {' AND '.join(where_clauses)}
            ORDER BY score DESC
            LIMIT ${len(params)}
        """
        rows = await self._pool.fetch(sql, *params)
        return [ScoredChunk(chunk=_row_to_chunk(row), score=row["score"]) for row in rows]

    async def delete_by_document(self, document_id: str) -> None:
        await self._pool.execute("DELETE FROM chunks_fts WHERE document_id = $1", document_id)


def _row_to_chunk(row: asyncpg.Record) -> Chunk:
    return Chunk(
        chunk_id=row["chunk_id"],
        document_id=row["document_id"],
        equipment_id=row["equipment_id"],
        manual_revision=row["manual_revision"],
        section_type=SectionType(row["section_type"]),
        section_title=row["section_title"],
        content=row["content"],
        order_index=row["order_index"],
        source_ref=row["source_ref"],
    )
