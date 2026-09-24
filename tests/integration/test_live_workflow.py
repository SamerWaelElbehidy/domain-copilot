"""End-to-end on the real stack: Qdrant + Postgres (a throwaway database,
so the dev data is never touched) + real Ollama embeddings. Only the chat
model is scripted, so the run is deterministic."""

import asyncio
import json
import os
import socket
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

import asyncpg
import httpx
import pytest

from application.agents.diagnostic_planner import DiagnosticSafetyPlanner
from application.agents.symptom_matcher import SymptomMatcher
from application.agents.tool_catalog import build_tool_registry
from application.agents.work_order_generator import WorkOrderGenerator
from application.ports.llm_provider import LLMProvider
from application.use_cases.orchestrator import CopilotOrchestrator
from application.use_cases.replay_run import replay_run
from application.use_cases.seed_corpus import seed_corpus
from config.prompts import load_prompt
from domain.entities.work_order import WorkOrderStatus
from domain.errors.domain_errors import TamperedRunError
from domain.value_objects.run_state import RunState
from infrastructure.corpus.loader import load_corpus
from infrastructure.llm.ollama_provider import OllamaProvider
from infrastructure.persistence.migrations import apply_migrations
from infrastructure.persistence.postgres_document_repository import PostgresDocumentRepository
from infrastructure.persistence.postgres_keyword_search_index import PostgresKeywordSearchIndex
from infrastructure.persistence.postgres_pool import create_pool
from infrastructure.persistence.postgres_run_repository import PostgresRunRepository
from infrastructure.persistence.postgres_work_order_repository import PostgresWorkOrderRepository
from infrastructure.vectorstore.qdrant_vector_store import QdrantVectorStore
from tests.fakes.fake_llm_provider import FakeLLMProvider
from tests.fakes.world import call_tool, say

CORPUS = Path(__file__).resolve().parents[2] / "corpus"
PG_PORT = int(os.environ.get("POSTGRES_PORT", "5433"))
SUBSET = ("cnc-wood-router-dwr2200", "air-compressor-iac100")


def _reachable(port: int) -> bool:
    try:
        with socket.create_connection(("localhost", port), timeout=1):
            return True
    except OSError:
        return False


def _ollama_up() -> bool:
    try:
        httpx.get("http://localhost:11434/api/version", timeout=2.0)
        return True
    except httpx.HTTPError:
        return False


requires_stack = pytest.mark.skipif(
    not (_reachable(6333) and _reachable(PG_PORT) and _ollama_up()),
    reason="needs Qdrant, Postgres (docker compose up) and Ollama running",
)


class ScriptedChatRealEmbeddings(LLMProvider):
    """Chat is scripted (deterministic); embeddings are real Ollama."""

    def __init__(self, chat: FakeLLMProvider, embedder: OllamaProvider) -> None:
        self._chat, self._embedder = chat, embedder

    async def complete(self, messages, tools=None):
        return await self._chat.complete(messages, tools)

    def stream(self, messages, tools=None):
        return self._chat.stream(messages, tools)

    async def embed(self, texts):
        return await self._embedder.embed(texts)


@asynccontextmanager
async def isolated_stack():
    suffix = uuid.uuid4().hex[:8]
    db_name = f"dc_test_{suffix}"
    admin = await asyncpg.connect(
        user=os.environ.get("POSTGRES_USER", "domain_copilot"),
        password=os.environ.get("POSTGRES_PASSWORD", "domain_copilot_dev"),
        database="postgres",
        host="localhost",
        port=PG_PORT,
    )
    await admin.execute(f'CREATE DATABASE "{db_name}"')
    pool = await create_pool(database=db_name)
    vector_store = QdrantVectorStore(collection_name=f"test_{suffix}", vector_size=768)
    try:
        async with pool.acquire() as conn:
            await apply_migrations(conn)
        await vector_store.ensure_collection()
        yield pool, vector_store
    finally:
        await pool.close()
        await admin.execute(f'DROP DATABASE IF EXISTS "{db_name}" WITH (FORCE)')
        await admin.close()
        await vector_store._client.delete_collection(f"test_{suffix}")


async def _scenario():
    async with isolated_stack() as (pool, vector_store):
        documents = PostgresDocumentRepository(pool)
        keyword_index = PostgresKeywordSearchIndex(pool)
        work_orders = PostgresWorkOrderRepository(pool)
        runs = PostgresRunRepository(pool)
        chat = FakeLLMProvider()
        llm = ScriptedChatRealEmbeddings(chat, OllamaProvider())

        items = [
            i for i in load_corpus(CORPUS) if any(s in i.document.document_id for s in
                                                  ("cnc-router", "air-compressor"))
        ]
        reports = await seed_corpus(
            items,
            llm_provider=llm,
            vector_store=vector_store,
            keyword_index=keyword_index,
            document_repository=documents,
        )
        statuses = {
            r["document_id"]: r["ingestion_status"]
            for r in await pool.fetch("SELECT document_id, ingestion_status FROM manual_documents")
        }

        registry = build_tool_registry(
            llm_provider=llm,
            vector_store=vector_store,
            keyword_index=keyword_index,
            document_repository=documents,
            work_order_repository=work_orders,
        )
        diag_id = await pool.fetchval(
            "SELECT chunk_id FROM chunks_fts WHERE document_id = $1 AND section_type = 'diagnostic'"
            " AND content ILIKE '%spindle overheating%'",
            "doc-cnc-router-dwr2200-rev-c",
        )
        chat._responses.extend(
            [
                call_tool("search_manual_chunks", {"query": "spindle overheating", "top_k": 5}),
                say(json.dumps({"equipment_id": "eq-cnc-router-dwr2200"})),
                say(json.dumps({"steps": [{"text": "Check the cooling intake.",
                                            "chunk_id": diag_id}]})),
                say(json.dumps({"summary": "Spindle overheats on long runs."})),
            ]
        )
        orchestrator = CopilotOrchestrator(
            matcher=SymptomMatcher(
                llm=llm, registry=registry, document_repository=documents,
                system_prompt=load_prompt("symptom_matcher").text,
            ),
            planner=DiagnosticSafetyPlanner(
                llm=llm, registry=registry, system_prompt=load_prompt("diagnostic_planner").text
            ),
            generator=WorkOrderGenerator(
                llm=llm, registry=registry, system_prompt=load_prompt("work_order_generator").text
            ),
            registry=registry,
            run_repository=runs,
            work_order_repository=work_orders,
        )

        started = await orchestrator.start("spindle overheating during long runs")
        pending = await runs.get(started.run_id)
        work_order = await work_orders.get(
            pending.steps[3].output_snapshot["result"]["work_order_id"]
        )
        done = await orchestrator.decide(
            started.run_id, reviewer="supervisor-1", decision="approve"
        )
        final = await runs.get(started.run_id)
        final_wo = await work_orders.get(work_order.work_order_id)
        first_replay = [f.name for f in replay_run(final)]

        forged = json.dumps({"result": {"equipment_id": "x"}})
        await pool.execute(
            "UPDATE run_steps SET output_snapshot = $2::jsonb WHERE run_id = $1 AND step_index = 1",
            started.run_id,
            forged,
        )
        tampered = await runs.get(started.run_id)
        return {
            "reports": reports, "statuses": statuses, "pending": pending, "work_order": work_order,
            "done": done, "final": final, "final_wo": final_wo, "first_replay": first_replay,
            "tampered": tampered,
        }


@requires_stack
def test_full_workflow_on_the_real_stack_with_persisted_audit_trail():
    out = asyncio.run(_scenario())

    assert all(r.status == "ingested" for r in out["reports"])
    assert set(out["statuses"].values()) == {"ingested"}

    pending = out["pending"]
    assert pending.state == RunState.PENDING_APPROVAL
    assert pending.verify_chain()
    documents_cited = {c.document_id for c in out["work_order"].citations}
    assert "doc-cnc-router-dwr2200-rev-b" not in documents_cited  # superseded never cited
    assert len(out["work_order"].safety_checklist) == 13

    assert out["done"].state == RunState.DISPATCHED
    assert out["final_wo"].status == WorkOrderStatus.DISPATCHED
    assert out["final"].verify_chain()
    assert out["first_replay"][-1] == "dispatch"

    tampered = out["tampered"]
    assert not tampered.verify_chain()
    with pytest.raises(TamperedRunError):
        list(replay_run(tampered))
