"""Lab step 2: why hybrid retrieval, and what rank fusion does.

Needs the running stack (`docker compose up`), because it uses the real
embedding model. From the repository root:

    python teaching/lab/02_retrieval.py "DWR-2200 spindle overheating"
    python teaching/lab/02_retrieval.py "the machine gets too hot when running for hours"

It prints, for the same question: what dense (meaning) search finds, what keyword
(exact words) search finds, and the fused order. Retrieval is limited to current
manual revisions, exactly as the product does.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from application.use_cases.hybrid_search import RRF_K  # noqa: E402
from config.settings import Settings  # noqa: E402
from infrastructure.llm.ollama_provider import OllamaProvider  # noqa: E402
from infrastructure.persistence.postgres_document_repository import (  # noqa: E402
    PostgresDocumentRepository,
)
from infrastructure.persistence.postgres_keyword_search_index import (  # noqa: E402
    PostgresKeywordSearchIndex,
)
from infrastructure.persistence.postgres_pool import create_pool  # noqa: E402
from infrastructure.vectorstore.qdrant_vector_store import QdrantVectorStore  # noqa: E402


def label(chunk) -> str:
    return f"{chunk.document_id.replace('doc-', '')} | {chunk.source_ref}"


async def main(query: str) -> None:
    settings = Settings.from_env()
    llm = OllamaProvider(base_url=settings.ollama_base_url, embed_model=settings.ollama_embed_model)
    vectors = QdrantVectorStore(
        url=settings.qdrant_url,
        collection_name=settings.qdrant_collection,
        vector_size=settings.embedding_dim,
    )
    pool = await create_pool()
    try:
        current = await PostgresDocumentRepository(pool).list_current_document_ids()
        filters = {"document_id": current}
        (embedding,) = await llm.embed([query])
        dense = await vectors.search(embedding, top_k=10, filters=filters)
        keyword = await PostgresKeywordSearchIndex(pool).search(query, top_k=10, filters=filters)
    finally:
        await pool.close()

    print(f"query: {query!r}\n")
    print("DENSE only (meaning):")
    for rank, item in enumerate(dense[:3], start=1):
        print(f"  {rank}. {label(item.chunk)}  (cosine {item.score:.2f})")
    print("KEYWORD only (all query words must appear):")
    for rank, item in enumerate(keyword[:3], start=1):
        print(f"  {rank}. {label(item.chunk)}")
    if not keyword:
        print("  (no chunk contains every query word)")

    fused: dict[str, float] = {}
    by_id = {}
    for ranked in (dense, keyword):
        for rank, item in enumerate(ranked):
            fused[item.chunk.chunk_id] = fused.get(item.chunk.chunk_id, 0.0) + 1 / (
                RRF_K + rank + 1
            )
            by_id[item.chunk.chunk_id] = item.chunk
    print(f"FUSED (Reciprocal Rank Fusion, k={RRF_K}; ranks only, scores never compared):")
    for rank, chunk_id in enumerate(sorted(fused, key=fused.get, reverse=True)[:3], start=1):
        print(f"  {rank}. {label(by_id[chunk_id])}  (fused {fused[chunk_id]:.4f})")


if __name__ == "__main__":
    asyncio.run(main(" ".join(sys.argv[1:]) or "DWR-2200 spindle overheating"))
