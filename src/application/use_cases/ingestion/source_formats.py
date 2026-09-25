from __future__ import annotations

from collections.abc import Mapping

from application.ports.pdf_text_extractor import PdfTextExtractor
from application.use_cases.ingestion.extract_pdf import pdf_to_markdown
from domain.errors.domain_errors import UnsupportedDocumentError

_PDF_MAGIC = b"%PDF-"


def to_markdown_source(
    *,
    filename: str,
    content: bytes,
    metadata: Mapping[str, str],
    pdf_extractor: PdfTextExtractor,
) -> str:
    """Turns an uploaded file into the Markdown the ingestion pipeline reads.
    The type is decided from the content, not the name, so a renamed file
    cannot slip through (OWASP: validated uploads). Two formats are accepted:
    Markdown (metadata in its own frontmatter) and PDF (metadata supplied)."""
    if content.startswith(_PDF_MAGIC):
        return pdf_to_markdown(content, metadata, pdf_extractor)
    if not filename.lower().endswith((".md", ".markdown")):
        raise UnsupportedDocumentError("only PDF and Markdown documents are accepted")
    if b"\x00" in content:
        raise UnsupportedDocumentError("file is binary, not Markdown text")
    try:
        return content.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise UnsupportedDocumentError("Markdown must be UTF-8 text") from exc
