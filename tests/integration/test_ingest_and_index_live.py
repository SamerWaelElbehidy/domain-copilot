import asyncio
from pathlib import Path

import httpx
import pytest

from application.use_cases.ingest_and_index_document import ingest_and_index_markdown_document
from infrastructure.llm.ollama_provider import OllamaProvider
from tests.fakes.fake_keyword_search_index import FakeKeywordSearchIndex
from tests.fakes.fake_vector_store import FakeVectorStore

CORPUS_ROOT = Path(__file__).resolve().parents[2] / "corpus"
MANUAL_PATH = CORPUS_ROOT / "cnc-wood-router-dwr2200" / "manual-rev-c.md"


def _ollama_available() -> bool:
    try:
        httpx.get("http://localhost:11434/api/version", timeout=2.0)
        return True
    except httpx.HTTPError:
        return False


@pytest.mark.skipif(not _ollama_available(), reason="Ollama server not reachable")
def test_full_pipeline_with_real_embeddings_indexes_into_both_stores():
    """extract -> clean -> chunk -> embed (real Ollama) -> index (fake
    stores, since Qdrant/Postgres aren't up yet). Proves the whole FR-1
    pipeline end-to-end with a real embedding model, independent of
    Docker being available."""
    raw_text = MANUAL_PATH.read_text(encoding="utf-8")
    llm_provider = OllamaProvider(embed_model="nomic-embed-text")
    vector_store = FakeVectorStore()
    keyword_index = FakeKeywordSearchIndex()

    chunks = asyncio.run(
        ingest_and_index_markdown_document(
            raw_text=raw_text,
            llm_provider=llm_provider,
            vector_store=vector_store,
            keyword_index=keyword_index,
        )
    )

    assert len(chunks) > 0
    assert len(vector_store.upserted) == len(chunks)
    assert len(keyword_index.indexed) == len(chunks)
    assert {c.chunk_id for c in vector_store.upserted} == {c.chunk_id for c in chunks}
