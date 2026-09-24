from __future__ import annotations

from typing import Any

from application.ports.document_repository import DocumentRepository
from application.ports.keyword_search_index import KeywordSearchIndex
from application.ports.llm_provider import LLMProvider
from application.ports.vector_store import VectorStore
from application.use_cases.hybrid_search import HybridResult, hybrid_search_detailed


async def scoped_search(
    *,
    llm_provider: LLMProvider,
    vector_store: VectorStore,
    keyword_index: KeywordSearchIndex,
    document_repository: DocumentRepository,
    query: str,
    equipment_id: str | None = None,
    section_type: str | None = None,
    top_k: int = 5,
) -> HybridResult:
    """The one retrieval path used by tools and the answerer. It is always
    restricted to non-superseded documents, so a stale revision can never be
    retrieved, and can be narrowed by equipment and section type."""
    current_ids = await document_repository.list_current_document_ids(equipment_id)
    if not current_ids:
        return HybridResult(chunks=[], top_dense_score=0.0)
    filters: dict[str, Any] = {"document_id": current_ids}
    if equipment_id:
        filters["equipment_id"] = equipment_id
    if section_type:
        filters["section_type"] = section_type
    embedding = (await llm_provider.embed([query]))[0]
    return await hybrid_search_detailed(
        vector_store=vector_store,
        keyword_index=keyword_index,
        query_embedding=embedding,
        query_text=query,
        top_k=top_k,
        filters=filters,
    )
