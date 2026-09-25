from __future__ import annotations

import re
from collections.abc import Mapping
from datetime import date

from application.ports.document_repository import DocumentRepository
from application.ports.keyword_search_index import KeywordSearchIndex
from application.ports.llm_provider import LLMProvider
from application.ports.pdf_text_extractor import PdfTextExtractor
from application.ports.vector_store import VectorStore
from application.use_cases.ingest_and_index_document import ingest_and_index_markdown_document
from application.use_cases.ingestion.extract_markdown import extract_markdown_document
from application.use_cases.ingestion.source_formats import to_markdown_source
from application.use_cases.seed_corpus import DocumentReport
from domain.entities.equipment import Equipment
from domain.entities.manual_document import ManualDocument
from domain.errors.domain_errors import UnsupportedDocumentError

_ID = re.compile(r"^[a-z0-9][a-z0-9-]{2,63}$")
_DOC_TYPES = {"manual", "loto", "bulletin", "policy"}
_STATUSES = {"current", "superseded"}
_MODEL = re.compile(r"[A-Z]{2,}-?\d+[A-Z0-9-]*")


def _validated_metadata(meta: Mapping[str, str]) -> dict[str, str]:
    """Metadata decides what the document is allowed to be retrieved for, so
    it is validated like any other input rather than trusted because an
    admin uploaded it."""
    missing = [
        k for k in ("equipment_id", "document_id", "revision", "effective_date") if not meta.get(k)
    ]
    if missing:
        raise UnsupportedDocumentError(f"missing required metadata: {missing}")
    for key in ("equipment_id", "document_id"):
        if not _ID.match(meta[key]):
            raise UnsupportedDocumentError(
                f"{key} must be 3-64 lowercase letters, digits or hyphens"
            )
    if len(meta["revision"]) > 32:
        raise UnsupportedDocumentError("revision is too long")
    try:
        date.fromisoformat(meta["effective_date"])
    except ValueError as exc:
        raise UnsupportedDocumentError("effective_date must be YYYY-MM-DD") from exc
    if meta.get("doc_type", "manual") not in _DOC_TYPES:
        raise UnsupportedDocumentError(f"doc_type must be one of {sorted(_DOC_TYPES)}")
    if meta.get("status", "current") not in _STATUSES:
        raise UnsupportedDocumentError(f"status must be one of {sorted(_STATUSES)}")
    return dict(meta)


async def upload_document(
    *,
    filename: str,
    content: bytes,
    metadata: Mapping[str, str],
    pdf_extractor: PdfTextExtractor,
    llm_provider: LLMProvider,
    vector_store: VectorStore,
    keyword_index: KeywordSearchIndex,
    document_repository: DocumentRepository,
) -> DocumentReport:
    """Admin ingestion of one PDF or Markdown file (FR-1). Anything wrong
    with the file or its metadata raises UnsupportedDocumentError before
    anything is written; a failure after that point is recorded against the
    document with its reason instead of leaving a half-ingested silent state."""
    raw_text = to_markdown_source(
        filename=filename, content=content, metadata=metadata, pdf_extractor=pdf_extractor
    )
    parsed = extract_markdown_document(raw_text)
    # For Markdown the file's own frontmatter is authoritative; for PDF the
    # frontmatter was built from the supplied metadata.
    meta = _validated_metadata({**{k: v for k, v in metadata.items() if v}, **parsed.metadata})

    document_id, equipment_id = meta["document_id"], meta["equipment_id"]
    existing = await document_repository.get_document(document_id)
    if existing is not None and existing.equipment_id != equipment_id:
        # Re-ingesting a document is fine (idempotent); silently moving a
        # safety document to a different machine is not.
        raise UnsupportedDocumentError(
            f"document_id '{document_id}' already belongs to another piece of equipment"
        )

    equipment = await document_repository.get_equipment(equipment_id)
    if equipment is None:
        name = meta.get("equipment_name")
        if not name:
            raise UnsupportedDocumentError("equipment_name is required for new equipment")
        model = _MODEL.search(name)
        equipment = Equipment(
            equipment_id=equipment_id,
            name=name,
            model_number=model.group(0) if model else "n/a",
            category="industrial",
        )
    title = next(
        (ln[2:].strip() for ln in parsed.body.splitlines() if ln.startswith("# ")), document_id
    )

    await document_repository.save_equipment(equipment)
    await document_repository.save_document(
        ManualDocument(
            document_id=document_id,
            equipment_id=equipment_id,
            revision=meta["revision"],
            effective_date=date.fromisoformat(meta["effective_date"]),
            title=title[:200],
            doc_type=meta.get("doc_type", "manual"),
            status=meta.get("status", "current"),
        )
    )
    try:
        chunks = await ingest_and_index_markdown_document(
            raw_text=raw_text,
            llm_provider=llm_provider,
            vector_store=vector_store,
            keyword_index=keyword_index,
        )
    except Exception as exc:  # noqa: BLE001 - recorded against the document
        await document_repository.set_ingestion_status(document_id, "failed", str(exc))
        return DocumentReport(document_id, "failed", error=str(exc))
    await document_repository.set_ingestion_status(document_id, "ingested")
    return DocumentReport(document_id, "ingested", chunks=len(chunks))
