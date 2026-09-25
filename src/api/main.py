"""Composition root: the only place that knows about Postgres, Qdrant and
concrete adapters. Run with `PYTHONPATH=src uvicorn api.main:app`."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI

from api.app import create_app
from api.container import Container
from api.rate_limit import TokenBucketLimiter
from application.llm_recording import RecordingLLMProvider
from application.use_cases.answer_question import GroundedAnswerer
from application.use_cases.authenticate_user import make_dummy_hash
from config.api_settings import ApiSettings
from config.prompts import load_prompt
from config.settings import Settings
from infrastructure.llm.ollama_provider import OllamaProvider
from infrastructure.persistence.postgres_chat_session_repository import (
    PostgresChatSessionRepository,
)
from infrastructure.persistence.postgres_document_repository import PostgresDocumentRepository
from infrastructure.persistence.postgres_keyword_search_index import PostgresKeywordSearchIndex
from infrastructure.persistence.postgres_llm_call_repository import PostgresLLMCallRepository
from infrastructure.persistence.postgres_pool import create_pool
from infrastructure.persistence.postgres_user_repository import PostgresUserRepository
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
    answerer = GroundedAnswerer(
        llm=llm,
        vector_store=QdrantVectorStore(
            url=settings.qdrant_url,
            collection_name=settings.qdrant_collection,
            vector_size=settings.embedding_dim,
        ),
        keyword_index=PostgresKeywordSearchIndex(pool),
        document_repository=PostgresDocumentRepository(pool),
        system_prompt=load_prompt("answer_question", "v3").text,
        min_dense_score=settings.relevance_threshold,
    )
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
    )
    try:
        yield
    finally:
        await pool.close()


app = create_app(api_settings, lifespan=lifespan)
