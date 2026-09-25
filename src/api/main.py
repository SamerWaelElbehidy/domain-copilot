"""Composition root: the only place that knows about Postgres, Qdrant and
concrete adapters. Run with `PYTHONPATH=src uvicorn api.main:app`."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI

from api.app import create_app
from api.container import Container, IngestionDeps
from api.rate_limit import TokenBucketLimiter
from api.run_manager import RunManager
from application.agents.diagnostic_planner import DiagnosticSafetyPlanner
from application.agents.symptom_matcher import SymptomMatcher
from application.agents.tool_catalog import build_tool_registry
from application.agents.work_order_generator import WorkOrderGenerator
from application.llm_recording import RecordingLLMProvider
from application.use_cases.answer_question import GroundedAnswerer
from application.use_cases.authenticate_user import make_dummy_hash
from application.use_cases.orchestrator import CopilotOrchestrator
from config.api_settings import ApiSettings
from config.prompts import load_prompt
from config.settings import Settings
from infrastructure.documents.pypdf_extractor import PypdfTextExtractor
from infrastructure.llm.ollama_provider import OllamaProvider
from infrastructure.persistence.postgres_chat_session_repository import (
    PostgresChatSessionRepository,
)
from infrastructure.persistence.postgres_document_repository import PostgresDocumentRepository
from infrastructure.persistence.postgres_keyword_search_index import PostgresKeywordSearchIndex
from infrastructure.persistence.postgres_llm_call_repository import PostgresLLMCallRepository
from infrastructure.persistence.postgres_pool import create_pool
from infrastructure.persistence.postgres_run_repository import PostgresRunRepository
from infrastructure.persistence.postgres_user_repository import PostgresUserRepository
from infrastructure.persistence.postgres_work_order_repository import (
    PostgresWorkOrderRepository,
)
from infrastructure.security.jwt_token_service import JwtTokenService
from infrastructure.security.password_hasher import ScryptPasswordHasher
from infrastructure.vectorstore.qdrant_vector_store import QdrantVectorStore

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")

api_settings = ApiSettings.from_env()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = Settings.from_env()
    pool = await create_pool()
    hasher = ScryptPasswordHasher()

    async def postgres_ok() -> bool:
        return await pool.fetchval("SELECT 1") == 1

    async def qdrant_ok() -> bool:
        async with httpx.AsyncClient(timeout=3.0) as client:
            return (await client.get(f"{settings.qdrant_url}/readyz")).status_code == 200

    async def llm_ok() -> bool:
        async with httpx.AsyncClient(timeout=3.0) as client:
            return (await client.get(f"{settings.ollama_base_url}/api/version")).status_code == 200

    llm_calls = PostgresLLMCallRepository(pool)
    llm = RecordingLLMProvider(
        OllamaProvider(
            base_url=settings.ollama_base_url,
            chat_model=settings.ollama_chat_model,
            embed_model=settings.ollama_embed_model,
            timeout_seconds=120.0,
        ),
        llm_calls,
        provider_name="ollama",
    )
    vector_store = QdrantVectorStore(
        url=settings.qdrant_url,
        collection_name=settings.qdrant_collection,
        vector_size=settings.embedding_dim,
    )
    keyword_index = PostgresKeywordSearchIndex(pool)
    documents = PostgresDocumentRepository(pool)
    answerer = GroundedAnswerer(
        llm=llm,
        vector_store=vector_store,
        keyword_index=keyword_index,
        document_repository=documents,
        system_prompt=load_prompt("answer_question", "v3").text,
        min_dense_score=settings.relevance_threshold,
    )
    run_repository = PostgresRunRepository(pool)
    work_orders = PostgresWorkOrderRepository(pool)
    registry = build_tool_registry(
        llm_provider=llm,
        vector_store=vector_store,
        keyword_index=keyword_index,
        document_repository=documents,
        work_order_repository=work_orders,
    )
    run_manager = RunManager()

    async def plain_rag_fallback(symptom: str) -> dict:
        # Graceful degradation (FR-5): if the multi-agent path keeps failing,
        # answer with plain grounded RAG instead of nothing.
        return (await answerer.answer(symptom)).as_dict()

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
        run_repository=run_repository,
        work_order_repository=work_orders,
        fallback=plain_rag_fallback,
        emit=run_manager.publish,
    )
    run_manager.bind(orchestrator)
    app.state.container = Container(
        settings=api_settings,
        users=PostgresUserRepository(pool),
        hasher=hasher,
        tokens=JwtTokenService(api_settings.jwt_secret, api_settings.jwt_ttl_minutes),
        dummy_hash=make_dummy_hash(hasher),
        login_limiter=TokenBucketLimiter(api_settings.login_attempts_per_minute),
        readiness_checks={"postgres": postgres_ok, "qdrant": qdrant_ok, "llm": llm_ok},
        answerer=answerer,
        sessions=PostgresChatSessionRepository(pool),
        llm_calls=llm_calls,
        ask_limiter=TokenBucketLimiter(api_settings.ask_per_minute),
        runs=run_repository,
        orchestrator=orchestrator,
        run_manager=run_manager,
        documents=documents,
        ingestion=IngestionDeps(
            pdf_extractor=PypdfTextExtractor(),
            llm_provider=llm,
            vector_store=vector_store,
            keyword_index=keyword_index,
            document_repository=documents,
        ),
    )
    try:
        yield
    finally:
        await pool.close()


app = create_app(api_settings, lifespan=lifespan)
