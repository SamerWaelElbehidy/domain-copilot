from __future__ import annotations

from application.ports.keyword_search_index import KeywordSearchIndex
from application.ports.llm_provider import LLMProvider
from application.ports.vector_store import VectorStore
from application.use_cases.ingest_document import ingest_markdown_document
from domain.entities.chunk import Chunk


async def ingest_and_index_markdown_document(
    *,
    raw_text: str,
    llm_provider: LLMProvider,
    vector_store: VectorStore,
    keyword_index: KeywordSearchIndex,
) -> list[Chunk]:
    """Full FR-1 pipeline: extract -> clean -> chunk (ingest_document.py)
    -> embed -> index. Deletes any existing chunks for the document first,
    so re-running ingestion on an unchanged or edited source is idempotent
    (FR-1) rather than accumulating duplicate/stale chunks."""
    chunks = ingest_markdown_document(raw_text)
    if not chunks:
        return chunks

    document_id = chunks[0].document_id
    await vector_store.delete_by_document(document_id)
    await keyword_index.delete_by_document(document_id)

    embeddings = await llm_provider.embed([chunk.content for chunk in chunks])
    await vector_store.upsert(chunks, embeddings)
    await keyword_index.index(chunks)

    return chunks
