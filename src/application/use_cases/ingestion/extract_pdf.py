from __future__ import annotations

import re
from collections import Counter
from collections.abc import Mapping

from application.ports.pdf_text_extractor import PdfTextExtractor
from application.use_cases.ingestion.chunk_document import KNOWN_HEADINGS
from domain.errors.domain_errors import NoExtractableTextError

_PAGE_NUMBER = re.compile(r"^(page\s+)?\d+(\s*(/|of)\s*\d+)?$", re.IGNORECASE)
_NUMBERED_HEADING = re.compile(r"^(\d+[.)]\s*)?(?P<title>.+?)\s*$")
FRONTMATTER_KEYS = (
    "equipment_id", "equipment_name", "document_id", "revision", "effective_date", "status",
)


def _strip_running_headers(pages: list[list[str]]) -> list[list[str]]:
    """Removes lines repeated on at least half the pages (running headers and
    footers) and bare page numbers, which would otherwise be chunked as content."""
    if len(pages) >= 2:
        counts = Counter(line for page in pages for line in set(page) if len(line) < 100)
        repeated = {line for line, n in counts.items() if n >= max(2, len(pages) / 2)}
    else:
        repeated = set()
    return [
        [ln for ln in page if ln not in repeated and not _PAGE_NUMBER.match(ln)]
        for page in pages
    ]


def _as_heading(line: str) -> str | None:
    """A line that is exactly a known section name becomes a `##` heading, so
    the same structure-aware chunker (ADR-0002) serves every input format."""
    match = _NUMBERED_HEADING.match(line)
    if match and match.group("title").lower() in KNOWN_HEADINGS:
        return match.group("title")
    return None


def pdf_to_markdown(
    pdf_bytes: bytes, metadata: Mapping[str, str], extractor: PdfTextExtractor
) -> str:
    """Extract stage (FR-1) for the PDF input format. Produces Markdown with
    the frontmatter the pipeline needs, so clean -> chunk -> embed -> index
    are shared with the Markdown format and PDF chunks obey the same
    atomic-safety-step rule."""
    pages = [
        [ln.strip() for ln in text.splitlines() if ln.strip()]
        for text in extractor.extract_pages(pdf_bytes)
    ]
    lines = [ln for page in _strip_running_headers(pages) for ln in page]
    if not lines:
        raise NoExtractableTextError(
            "the PDF has no text layer (a scan?); OCR is not supported for this variant"
        )

    body: list[str] = []
    title_written = False
    for line in lines:
        heading = _as_heading(line)
        if heading:
            body += ["", f"## {heading}", ""]
        elif not title_written:
            body += [f"# {line}", ""]
            title_written = True
        else:
            body.append(line)

    frontmatter = [f"{k}: {metadata[k]}" for k in FRONTMATTER_KEYS if k in metadata]
    return "---\n" + "\n".join(frontmatter) + "\n---\n\n" + "\n".join(body).strip() + "\n"
