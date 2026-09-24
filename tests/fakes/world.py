from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from application.agents.tool_catalog import build_tool_registry
from application.agents.tool_registry import ToolRegistry
from application.ports.llm_provider import CompletionResult, ToolCall
from application.use_cases.ingest_and_index_document import ingest_and_index_markdown_document
from infrastructure.corpus.loader import load_corpus
from tests.fakes.fake_llm_provider import FakeLLMProvider
from tests.fakes.in_memory import (
    InMemoryDocumentRepository,
    InMemoryKeywordIndex,
    InMemoryVectorStore,
    InMemoryWorkOrderRepository,
)

CORPUS_ROOT = Path(__file__).resolve().parents[2] / "corpus"
FIXED_NOW = datetime(2026, 1, 1, 12, 0, 0)


@dataclass
class World:
    """The whole real corpus ingested into in-memory stores, with a scripted
    LLM. Lets agent tests run against real documents with no network."""

    llm: FakeLLMProvider
    vector_store: InMemoryVectorStore
    keyword_index: InMemoryKeywordIndex
    documents: InMemoryDocumentRepository
    work_orders: InMemoryWorkOrderRepository
    registry: ToolRegistry

    def chunk_id(self, document_id: str, section: str, contains: str) -> str:
        for chunk in self.vector_store.chunks.values():
            if (
                chunk.document_id == document_id
                and chunk.section_type.value == section
                and contains in chunk.content
            ):
                return chunk.chunk_id
        raise LookupError(f"no {section} chunk in {document_id} containing {contains!r}")


def build_world(scripted: list[CompletionResult] | None = None) -> World:
    llm = FakeLLMProvider(responses=scripted or [], embedding_dim=256)
    vector_store, keyword_index = InMemoryVectorStore(), InMemoryKeywordIndex()
    documents, work_orders = InMemoryDocumentRepository(), InMemoryWorkOrderRepository()

    async def ingest_all() -> None:
        for item in load_corpus(CORPUS_ROOT):
            await documents.save_equipment(item.equipment)
            await documents.save_document(item.document)
            await ingest_and_index_markdown_document(
                raw_text=item.raw_text,
                llm_provider=llm,
                vector_store=vector_store,
                keyword_index=keyword_index,
            )

    asyncio.run(ingest_all())
    counter = iter(range(1, 1000))
    registry = build_tool_registry(
        llm_provider=llm,
        vector_store=vector_store,
        keyword_index=keyword_index,
        document_repository=documents,
        work_order_repository=work_orders,
        id_factory=lambda: f"wo-{next(counter)}",
        clock=lambda: FIXED_NOW,
    )
    return World(llm, vector_store, keyword_index, documents, work_orders, registry)


def say(text: str) -> CompletionResult:
    return CompletionResult(content=text, model="fake")


def call_tool(name: str, arguments: dict, call_id: str = "call-1") -> CompletionResult:
    return CompletionResult(
        content="", tool_calls=[ToolCall(id=call_id, name=name, arguments=arguments)], model="fake"
    )
