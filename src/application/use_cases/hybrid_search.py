from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from application.ports.keyword_search_index import KeywordSearchIndex
from application.ports.vector_store import VectorStore
from domain.entities.chunk import Chunk

RRF_K = 60


@dataclass(frozen=True)
class HybridResult:
    chunks: list[Chunk]
    # Best dense (cosine) similarity among candidates. RRF only keeps rank
    # order, so this is the signal used to decide there is no real evidence.
    top_dense_score: float


async def hybrid_search_detailed(
    *,
    vector_store: VectorStore,
    keyword_index: KeywordSearchIndex,
    query_embedding: list[float],
    query_text: str,
    top_k: int,
    filters: dict[str, Any] | None = None,
) -> HybridResult:
    """Fuses dense + keyword results via Reciprocal Rank Fusion (ADR-0004):
    each chunk's fused score is the sum of 1/(RRF_K + rank) over every
    ranker it appears in -- rank order only, so cosine similarity and
    ts_rank never need to share a comparable scale."""
    dense_results = await vector_store.search(query_embedding, top_k=top_k * 2, filters=filters)
    keyword_results = await keyword_index.search(query_text, top_k=top_k * 2, filters=filters)

    fused_scores: dict[str, float] = {}
    chunks_by_id: dict[str, Chunk] = {}

    for ranked_list in (dense_results, keyword_results):
        for rank, scored in enumerate(ranked_list):
            chunk_id = scored.chunk.chunk_id
            fused_scores[chunk_id] = fused_scores.get(chunk_id, 0.0) + 1.0 / (RRF_K + rank + 1)
            chunks_by_id[chunk_id] = scored.chunk

    ranked_ids = sorted(fused_scores, key=lambda cid: fused_scores[cid], reverse=True)
    return HybridResult(
        chunks=[chunks_by_id[chunk_id] for chunk_id in ranked_ids[:top_k]],
        top_dense_score=max((s.score for s in dense_results), default=0.0),
    )


async def hybrid_search(
    *,
    vector_store: VectorStore,
    keyword_index: KeywordSearchIndex,
    query_embedding: list[float],
    query_text: str,
    top_k: int,
    filters: dict[str, Any] | None = None,
) -> list[Chunk]:
    result = await hybrid_search_detailed(
        vector_store=vector_store,
        keyword_index=keyword_index,
        query_embedding=query_embedding,
        query_text=query_text,
        top_k=top_k,
        filters=filters,
    )
    return result.chunks
