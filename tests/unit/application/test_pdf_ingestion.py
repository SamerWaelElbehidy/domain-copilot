from collections import Counter
from pathlib import Path

import pytest

from application.use_cases.ingest_document import ingest_markdown_document
from application.use_cases.ingestion.extract_pdf import pdf_to_markdown
from application.use_cases.ingestion.source_formats import to_markdown_source
from domain.errors.domain_errors import NoExtractableTextError, UnsupportedDocumentError
from infrastructure.documents.pypdf_extractor import PypdfTextExtractor
from tests.fakes.pdf_builder import build_pdf, manual_pdf

ROOT = Path(__file__).resolve().parents[3]
ROUTER = ROOT / "corpus" / "cnc-wood-router-dwr2200" / "manual-rev-c.md"
METADATA = {
    "equipment_id": "eq-cnc-router-dwr2200",
    "equipment_name": "CNC Wood Router DWR-2200",
    "document_id": "doc-cnc-router-dwr2200-rev-c-pdf",
    "revision": "Rev. C",
    "effective_date": "2025-11-01",
}
EXTRACTOR = PypdfTextExtractor()


def section_counts(chunks) -> Counter:
    return Counter(c.section_type.value for c in chunks)


def test_a_pdf_manual_chunks_like_its_markdown_source():
    markdown = ROUTER.read_text(encoding="utf-8")
    from_markdown = ingest_markdown_document(markdown)

    source = pdf_to_markdown(manual_pdf(markdown), METADATA, EXTRACTOR)
    from_pdf = ingest_markdown_document(source)

    assert section_counts(from_pdf) == section_counts(from_markdown)
    assert section_counts(from_pdf)["safety_prerequisite"] == 7
    assert section_counts(from_pdf)["diagnostic"] == 4


def test_a_pdf_safety_step_stays_one_chunk_even_when_it_wraps_across_lines():
    source = pdf_to_markdown(manual_pdf(ROUTER.read_text(encoding="utf-8")), METADATA, EXTRACTOR)
    chunks = ingest_markdown_document(source)

    hose = [c for c in chunks if "dust extraction hose connection" in c.content]

    assert len(hose) == 1
    assert "green zone" in hose[0].content  # the qualifier is in the same chunk


def test_running_headers_and_page_numbers_are_not_chunked_as_content():
    source = pdf_to_markdown(manual_pdf(ROUTER.read_text(encoding="utf-8")), METADATA, EXTRACTOR)

    assert "Dawlia Furniture Works - Maintenance Manual" not in source
    assert "Page 1" not in source


def test_frontmatter_carries_the_supplied_metadata():
    source = pdf_to_markdown(build_pdf([["Manual", "Overview & Specifications", "text"]]),
                             METADATA, EXTRACTOR)

    assert "document_id: doc-cnc-router-dwr2200-rev-c-pdf" in source
    assert ingest_markdown_document(source)[0].manual_revision == "Rev. C"


def test_a_pdf_without_a_text_layer_is_reported_not_silently_empty():
    with pytest.raises(NoExtractableTextError):
        pdf_to_markdown(build_pdf([[""], [""]]), METADATA, EXTRACTOR)


def test_a_damaged_pdf_is_an_unsupported_document():
    with pytest.raises(UnsupportedDocumentError):
        EXTRACTOR.extract_pages(b"%PDF-1.4 this is not really a pdf")


def test_the_page_limit_is_enforced():
    pdf = build_pdf([["one"], ["two"], ["three"]])

    with pytest.raises(UnsupportedDocumentError):
        PypdfTextExtractor(max_pages=2).extract_pages(pdf)


# --- format detection is by content, not by file name -------------------------


def convert(filename: str, content: bytes) -> str:
    return to_markdown_source(
        filename=filename, content=content, metadata=METADATA, pdf_extractor=EXTRACTOR
    )


def test_markdown_is_accepted_as_is():
    text = ROUTER.read_text(encoding="utf-8")

    assert convert("manual.md", text.encode("utf-8")) == text


def test_a_pdf_is_recognised_by_its_content_even_with_a_misleading_name():
    pdf = build_pdf([["Manual", "Overview & Specifications", "some text here"]])

    assert "## Overview & Specifications" in convert("notes.txt", pdf)


@pytest.mark.parametrize(
    ("filename", "content"),
    [
        ("report.pdf", b"just plain text renamed to pdf"),
        ("tool.exe", b"MZ\x90\x00\x03"),
        ("manual.md", b"# title\x00\x01binary"),
        ("manual.md", b"\xff\xfe not utf-8 \xfa"),
        ("archive.zip", b"PK\x03\x04"),
    ],
)
def test_other_files_are_refused(filename, content):
    with pytest.raises(UnsupportedDocumentError):
        convert(filename, content)
