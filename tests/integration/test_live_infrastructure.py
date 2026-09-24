import asyncio
import os
import socket
import uuid
from datetime import date
from pathlib import Path

import httpx
import pytest

from application.use_cases.hybrid_search import hybrid_search
from application.use_cases.ingest_and_index_document import ingest_and_index_markdown_document
from domain.entities.equipment import Equipment
from domain.entities.manual_document import ManualDocument
from domain.value_objects.section_type import SectionType
from infrastructure.llm.ollama_provider import OllamaProvider
from infrastructure.persistence.postgres_document_repository import PostgresDocumentRepository
from infrastructure.persistence.postgres_keyword_search_index import PostgresKeywordSearchIndex
from infrastructure.persistence.postgres_pool import create_pool
from infrastructure.vectorstore.qdrant_vector_store import QdrantVectorStore

MANUAL_PATH = (
    Path(__file__).resolve().parents[2] / "corpus" / "cnc-wood-router-dwr2200" / "manual-rev-c.md"
)
QDRANT_URL = os.environ.get("QDRANT_URL", "http://localhost:6333")


def _reachable(host: str, port: int) -> bool:
    try:
        with socket.create_connection((host, port), timeout=1):
            return True
    except OSError:
        return False


def _ollama_up() -> bool:
    try:
        httpx.get("http://localhost:11434/api/version", timeout=2.0)
        return True
    except httpx.HTTPError:
        return False


pg_port = int(os.environ.get("POSTGRES_PORT", "5433"))
requires_stack = pytest.mark.skipif(
    not (_reachable("localhost", 6333) and _reachable("localhost", pg_port) and _ollama_up()),
    reason="needs Qdrant, Postgres (docker compose up) and Ollama running",
)


async def _run_pipeline_and_search():
    collection = f"test_{uuid.uuid4().hex[:8]}"
    llm = OllamaProvider(embed_model="nomic-embed-text")
    vector_store = QdrantVectorStore(url=QDRANT_URL, collection_name=collection, vector_size=768)
    pool = await create_pool()
    try:
        await vector_store.ensure_collection()
        repo = PostgresDocumentRepository(pool)
        keyword_index = PostgresKeywordSearchIndex(pool)

        await repo.save_equipment(
            Equipment("eq-cnc-router-dwr2200", "CNC Wood Router DWR-2200", "DWR-2200", "cnc")
        )
        await repo.save_document(
            ManualDocument(
                "doc-cnc-router-dwr2200-rev-c",
                "eq-cnc-router-dwr2200",
                "Rev. C",
                date(2025, 11, 1),
                "DWR-2200 Manual Rev. C",
            )
        )

        raw_text = MANUAL_PATH.read_text(encoding="utf-8")
        deps = {"llm_provider": llm, "vector_store": vector_store, "keyword_index": keyword_index}
        chunks = await ingest_and_index_markdown_document(raw_text=raw_text, **deps)
        # re-ingesting must be idempotent (FR-1)
        await ingest_and_index_markdown_document(raw_text=raw_text, **deps)
        stored = await pool.fetchval(
            "SELECT count(*) FROM chunks_fts WHERE document_id = $1",
            "doc-cnc-router-dwr2200-rev-c",
        )

        query = "dust extraction hose connection check before starting a job"
        query_embedding = (await llm.embed([query]))[0]
        results = await hybrid_search(
            vector_store=vector_store,
            keyword_index=keyword_index,
            query_embedding=query_embedding,
            query_text=query,
            top_k=5,
            filters={"equipment_id": "eq-cnc-router-dwr2200"},
        )
        return chunks, stored, results
    finally:
        await vector_store._client.delete_collection(collection)
        await pool.execute(
            "DELETE FROM chunks_fts WHERE document_id = $1", "doc-cnc-router-dwr2200-rev-c"
        )
        await pool.close()


@requires_stack
def test_real_qdrant_and_postgres_hybrid_retrieval_end_to_end():
    chunks, stored, results = asyncio.run(_run_pipeline_and_search())

    assert stored == len(chunks), "re-ingestion must not duplicate chunks"
    assert results, "hybrid search returned nothing"
    assert all(c.equipment_id == "eq-cnc-router-dwr2200" for c in results)
    assert any(
        c.section_type == SectionType.SAFETY_PREREQUISITE
        and "dust extraction hose connection" in c.content
        for c in results
    ), "the dust-hose safety prerequisite should be retrieved for this query"
