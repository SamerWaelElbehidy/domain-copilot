"""Seed/ingest command: loads the synthetic corpus into Postgres and Qdrant.

Usage: python scripts/seed.py
Requires `docker compose up -d`, `python scripts/migrate.py`, and a running
Ollama with the embedding model (see README).
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from application.use_cases.seed_corpus import seed_corpus  # noqa: E402
from config.settings import Settings  # noqa: E402
from infrastructure.corpus.loader import load_corpus  # noqa: E402
from infrastructure.llm.ollama_provider import OllamaProvider  # noqa: E402
from infrastructure.persistence.postgres_document_repository import (  # noqa: E402
    PostgresDocumentRepository,
)
from infrastructure.persistence.postgres_keyword_search_index import (  # noqa: E402
    PostgresKeywordSearchIndex,
)
from infrastructure.persistence.postgres_pool import create_pool  # noqa: E402
from infrastructure.vectorstore.qdrant_vector_store import QdrantVectorStore  # noqa: E402


async def main() -> int:
    settings = Settings.from_env()
    vector_store = QdrantVectorStore(
        url=settings.qdrant_url,
        collection_name=settings.qdrant_collection,
        vector_size=settings.embedding_dim,
    )
    await vector_store.ensure_collection()
    pool = await create_pool()
    try:
        reports = await seed_corpus(
            load_corpus(ROOT / "corpus"),
            llm_provider=OllamaProvider(
                base_url=settings.ollama_base_url, embed_model=settings.ollama_embed_model
            ),
            vector_store=vector_store,
            keyword_index=PostgresKeywordSearchIndex(pool),
            document_repository=PostgresDocumentRepository(pool),
        )
    finally:
        await pool.close()

    failed = [r for r in reports if r.status == "failed"]
    for report in reports:
        detail = f"{report.chunks} chunks" if report.status == "ingested" else report.error
        print(f"{report.status:9} {report.document_id}  ({detail})")
    print(f"\n{len(reports) - len(failed)} ingested, {len(failed)} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
