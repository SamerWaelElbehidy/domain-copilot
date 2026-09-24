from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

from application.ports.document_repository import DocumentRepository
from application.ports.keyword_search_index import KeywordSearchIndex
from application.ports.llm_provider import LLMProvider
from application.ports.vector_store import VectorStore
from application.use_cases.ingest_and_index_document import ingest_and_index_markdown_document
from domain.entities.equipment import Equipment
from domain.entities.manual_document import ManualDocument


class CorpusItem(Protocol):
    equipment: Equipment
    document: ManualDocument
    raw_text: str


@dataclass(frozen=True)
class DocumentReport:
    document_id: str
    status: str  # "ingested" | "failed"
    chunks: int = 0
    error: str | None = None


async def seed_corpus(
    items: Sequence[CorpusItem],
    *,
    llm_provider: LLMProvider,
    vector_store: VectorStore,
    keyword_index: KeywordSearchIndex,
    document_repository: DocumentRepository,
) -> list[DocumentReport]:
    """Ingests every document independently: one bad document is recorded
    as failed with its reason and the rest continue (FR-1 per-document
    status and failure reporting). Safe to re-run; ingestion is idempotent."""
    reports: list[DocumentReport] = []
    for item in items:
        document_id = item.document.document_id
        try:
            await document_repository.save_equipment(item.equipment)
            await document_repository.save_document(item.document)
            chunks = await ingest_and_index_markdown_document(
                raw_text=item.raw_text,
                llm_provider=llm_provider,
                vector_store=vector_store,
                keyword_index=keyword_index,
            )
            await document_repository.set_ingestion_status(document_id, "ingested")
            reports.append(DocumentReport(document_id, "ingested", chunks=len(chunks)))
        except Exception as exc:  # noqa: BLE001 - reported, not swallowed
            await document_repository.set_ingestion_status(document_id, "failed", str(exc))
            reports.append(DocumentReport(document_id, "failed", error=str(exc)))
    return reports
