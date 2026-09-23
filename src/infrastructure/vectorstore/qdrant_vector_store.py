from __future__ import annotations

import uuid
from typing import Any

from qdrant_client import AsyncQdrantClient
from qdrant_client.http import models as qmodels

from application.ports.vector_store import ScoredChunk, VectorStore
from domain.entities.chunk import Chunk
from domain.value_objects.section_type import SectionType


class QdrantVectorStore(VectorStore):
    """Dense-vector adapter (ADR-0004). Qdrant point ids must be a UUID
    or unsigned int, not an arbitrary string, so chunk_id is deterministically
    mapped to a UUID via uuid5 -- the original chunk_id is kept in the
    payload so results can round-trip back to a real Chunk."""

    def __init__(
        self,
        url: str = "http://localhost:6333",
        collection_name: str = "chunks",
        vector_size: int = 768,
    ) -> None:
        self._client = AsyncQdrantClient(url=url)
        self._collection_name = collection_name
        self._vector_size = vector_size

    async def ensure_collection(self) -> None:
        """Creates the collection and payload indexes if missing. Not
        part of the VectorStore port itself -- it's a one-time setup
        concern, called from the seed/ingest command, not per-request."""
        exists = await self._client.collection_exists(self._collection_name)
        if exists:
            return

        await self._client.create_collection(
            collection_name=self._collection_name,
            vectors_config=qmodels.VectorParams(
                size=self._vector_size, distance=qmodels.Distance.COSINE
            ),
        )
        for field_name in ("equipment_id", "manual_revision", "section_type", "document_id"):
            await self._client.create_payload_index(
                collection_name=self._collection_name,
                field_name=field_name,
                field_schema=qmodels.PayloadSchemaType.KEYWORD,
            )

    async def upsert(self, chunks: list[Chunk], embeddings: list[list[float]]) -> None:
        if not chunks:
            return
        points = [
            qmodels.PointStruct(
                id=_point_id(chunk.chunk_id),
                vector=embedding,
                payload=_chunk_to_payload(chunk),
            )
            for chunk, embedding in zip(chunks, embeddings, strict=True)
        ]
        await self._client.upsert(collection_name=self._collection_name, points=points)

    async def search(
        self,
        query_embedding: list[float],
        top_k: int,
        filters: dict[str, Any] | None = None,
    ) -> list[ScoredChunk]:
        response = await self._client.query_points(
            collection_name=self._collection_name,
            query=query_embedding,
            limit=top_k,
            query_filter=_build_filter(filters) if filters else None,
        )
        return [
            ScoredChunk(chunk=_payload_to_chunk(point.payload), score=point.score)
            for point in response.points
        ]

    async def delete_by_document(self, document_id: str) -> None:
        await self._client.delete(
            collection_name=self._collection_name,
            points_selector=qmodels.FilterSelector(
                filter=qmodels.Filter(
                    must=[
                        qmodels.FieldCondition(
                            key="document_id", match=qmodels.MatchValue(value=document_id)
                        )
                    ]
                )
            ),
        )


def _chunk_to_payload(chunk: Chunk) -> dict:
    return {
        "chunk_id": chunk.chunk_id,
        "document_id": chunk.document_id,
        "equipment_id": chunk.equipment_id,
        "manual_revision": chunk.manual_revision,
        "section_type": chunk.section_type.value,
        "section_title": chunk.section_title,
        "content": chunk.content,
        "order_index": chunk.order_index,
        "source_ref": chunk.source_ref,
    }


def _payload_to_chunk(payload: dict) -> Chunk:
    return Chunk(
        chunk_id=payload["chunk_id"],
        document_id=payload["document_id"],
        equipment_id=payload["equipment_id"],
        manual_revision=payload["manual_revision"],
        section_type=SectionType(payload["section_type"]),
        section_title=payload["section_title"],
        content=payload["content"],
        order_index=payload["order_index"],
        source_ref=payload["source_ref"],
    )


def _build_filter(filters: dict[str, Any]) -> qmodels.Filter:
    return qmodels.Filter(
        must=[
            qmodels.FieldCondition(key=key, match=qmodels.MatchValue(value=value))
            for key, value in filters.items()
        ]
    )


def _point_id(chunk_id: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, chunk_id))
