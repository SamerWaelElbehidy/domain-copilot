"""Runs the golden set against the live stack and reports retrieval hit-rate,
groundedness, refusal correctness and injection resistance (FR-3).

Usage:
  python scripts/evaluate.py [--chat-model llama3.2:1b] [--top-k 5]
                             [--min-dense-score 0.0] [--label baseline] [--limit N]

It uses its own database (dc_eval) and Qdrant collection (eval_chunks), so
the operational data is untouched. The adversarial fixtures in
eval/extra_corpus are indexed there and only there. The first run embeds
the whole corpus and takes several minutes; later runs reuse it.
Results are written to eval/results/<label>.json and .md.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import asyncpg  # noqa: E402

from application.use_cases.answer_question import GroundedAnswerer  # noqa: E402
from application.use_cases.seed_corpus import seed_corpus  # noqa: E402
from config.prompts import load_prompt  # noqa: E402
from config.settings import Settings  # noqa: E402
from evaluation.golden_set import load_golden_set  # noqa: E402
from evaluation.metrics import summarize, threshold_sweep  # noqa: E402
from evaluation.report import render_markdown  # noqa: E402
from evaluation.runner import run_evaluation  # noqa: E402
from infrastructure.corpus.loader import load_corpus  # noqa: E402
from infrastructure.llm.ollama_provider import OllamaProvider  # noqa: E402
from infrastructure.persistence.migrations import apply_migrations  # noqa: E402
from infrastructure.persistence.postgres_document_repository import (  # noqa: E402
    PostgresDocumentRepository,
)
from infrastructure.persistence.postgres_keyword_search_index import (  # noqa: E402
    PostgresKeywordSearchIndex,
)
from infrastructure.persistence.postgres_pool import create_pool  # noqa: E402
from infrastructure.vectorstore.qdrant_vector_store import QdrantVectorStore  # noqa: E402

EVAL_DB = "dc_eval"
EVAL_COLLECTION = "eval_chunks"


async def ensure_eval_database(settings: Settings) -> None:
    admin = await asyncpg.connect(
        user=settings.postgres_user,
        password=settings.postgres_password,
        database="postgres",
        host=settings.postgres_host,
        port=settings.postgres_port,
    )
    try:
        exists = await admin.fetchval("SELECT 1 FROM pg_database WHERE datname = $1", EVAL_DB)
        if not exists:
            await admin.execute(f'CREATE DATABASE "{EVAL_DB}"')
    finally:
        await admin.close()


async def main(args: argparse.Namespace) -> int:
    settings = Settings.from_env()
    llm = OllamaProvider(
        base_url=settings.ollama_base_url,
        chat_model=args.chat_model,
        embed_model=settings.ollama_embed_model,
        timeout_seconds=600.0,
    )
    await ensure_eval_database(settings)
    pool = await create_pool(database=EVAL_DB)
    vector_store = QdrantVectorStore(
        url=settings.qdrant_url, collection_name=EVAL_COLLECTION, vector_size=settings.embedding_dim
    )
    try:
        async with pool.acquire() as conn:
            await apply_migrations(conn)
        await vector_store.ensure_collection()
        documents = PostgresDocumentRepository(pool)
        keyword_index = PostgresKeywordSearchIndex(pool)

        done = {
            r["document_id"]
            for r in await pool.fetch(
                "SELECT document_id FROM manual_documents WHERE ingestion_status = 'ingested'"
            )
        }
        items = [
            i
            for i in load_corpus(ROOT / "corpus") + load_corpus(ROOT / "eval" / "extra_corpus")
            if i.document.document_id not in done
        ]
        if items:
            print(f"indexing {len(items)} documents into {EVAL_DB} / {EVAL_COLLECTION} ...")
            reports = await seed_corpus(
                items, llm_provider=llm, vector_store=vector_store,
                keyword_index=keyword_index, document_repository=documents,
            )
            failed = [r for r in reports if r.status == "failed"]
            if failed:
                print("ingestion failures:", *[f"{r.document_id}: {r.error}" for r in failed],
                      sep="\n  ")
                return 1

        cases = load_golden_set(ROOT / "eval" / "golden_set.json")
        if args.limit:
            cases = cases[: args.limit]
        answerer = GroundedAnswerer(
            llm=llm,
            vector_store=vector_store,
            keyword_index=keyword_index,
            document_repository=documents,
            system_prompt=load_prompt("answer_question", "v2").text,
            top_k=args.top_k,
            min_dense_score=args.min_dense_score,
        )

        def show(result) -> None:
            mark = "PASS" if result.passed else "FAIL"
            print(f"{mark} {result.case.id:4} {result.case.category:20} "
                  f"{result.observation.status:9} {result.observation.reason or ''}", flush=True)

        results = await run_evaluation(cases, answerer.answer, on_result=show)
    finally:
        await pool.close()

    summary = summarize(results)
    sweep = threshold_sweep(results, [round(0.05 * i, 2) for i in range(0, 17)])
    meta = {
        "label": args.label,
        "chat_model": args.chat_model,
        "embed_model": settings.ollama_embed_model,
        "top_k": args.top_k,
        "min_dense_score": args.min_dense_score,
    }
    out_dir = ROOT / "eval" / "results"
    out_dir.mkdir(exist_ok=True)
    (out_dir / f"{args.label}.md").write_text(
        render_markdown(summary, sweep, results, meta), encoding="utf-8"
    )
    (out_dir / f"{args.label}.json").write_text(
        json.dumps(
            {
                "meta": meta, "summary": summary, "sweep": sweep,
                "cases": [
                    {
                        "id": r.case.id, "category": r.case.category, "expect": r.case.expect,
                        "question": r.case.question, "passed": r.passed,
                        "status": r.observation.status, "reason": r.observation.reason,
                        "answer": r.observation.text,
                        "cited_documents": list(r.observation.cited_document_ids),
                        "retrieved_documents": list(r.observation.retrieved_document_ids),
                        "top_dense_score": r.observation.top_dense_score,
                        "groundedness": r.groundedness, "detail": r.detail,
                    }
                    for r in results
                ],
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    print(json.dumps(summary, indent=2))
    print(f"\nwritten: eval/results/{args.label}.md and .json")
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--chat-model", default=os.environ.get("OLLAMA_CHAT_MODEL", "llama3.2:1b"))
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--min-dense-score", type=float, default=0.0)
    parser.add_argument("--label", default="baseline")
    parser.add_argument("--limit", type=int, default=0)
    sys.exit(asyncio.run(main(parser.parse_args())))
