from __future__ import annotations

from application.use_cases.ingestion.chunk_document import chunk_document
from application.use_cases.ingestion.clean_text import clean_text
from application.use_cases.ingestion.extract_markdown import extract_markdown_document
from domain.entities.chunk import Chunk

_REQUIRED_KEYS = ("equipment_id", "document_id", "revision")


class MissingRequiredMetadataError(ValueError):
    """A source document's frontmatter is missing a key the pipeline
    needs -- fail at ingestion time, not with a confusing error deep in
    retrieval."""


def ingest_markdown_document(raw_text: str) -> list[Chunk]:
    """Ties extract -> clean -> chunk together for one Markdown source
    (FR-1). embed -> index are separate stages, wired in once the
    LLMProvider/VectorStore adapters exist (ADR-0003/0004)."""
    extracted = extract_markdown_document(raw_text)

    missing = [key for key in _REQUIRED_KEYS if key not in extracted.metadata]
    if missing:
        raise MissingRequiredMetadataError(
            f"Document is missing required frontmatter keys: {missing}"
        )

    cleaned_body = clean_text(extracted.body)

    return chunk_document(
        document_id=extracted.metadata["document_id"],
        equipment_id=extracted.metadata["equipment_id"],
        manual_revision=extracted.metadata["revision"],
        body=cleaned_body,
    )
