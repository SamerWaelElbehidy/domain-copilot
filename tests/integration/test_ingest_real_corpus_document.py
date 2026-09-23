from pathlib import Path

from application.use_cases.ingest_document import ingest_markdown_document
from domain.value_objects.section_type import SectionType

CORPUS_ROOT = Path(__file__).resolve().parents[2] / "corpus"
MANUAL_PATH = CORPUS_ROOT / "cnc-wood-router-dwr2200" / "manual-rev-c.md"


def _ingest_real_manual():
    raw_text = MANUAL_PATH.read_text(encoding="utf-8")
    return ingest_markdown_document(raw_text)


def test_ingesting_the_real_cnc_router_manual_produces_correctly_tagged_chunks():
    chunks = _ingest_real_manual()

    assert len(chunks) > 0
    assert all(c.equipment_id == "eq-cnc-router-dwr2200" for c in chunks)
    assert all(c.document_id == "doc-cnc-router-dwr2200-rev-c" for c in chunks)
    assert all(c.manual_revision == "Rev. C" for c in chunks)


def test_all_seven_safety_prerequisites_become_separate_atomic_chunks():
    chunks = _ingest_real_manual()
    safety_chunks = [c for c in chunks if c.section_type == SectionType.SAFETY_PREREQUISITE]

    assert len(safety_chunks) == 7
    dust_hose_chunks = [c for c in safety_chunks if "dust extraction hose connection" in c.content]
    assert len(dust_hose_chunks) == 1
    assert "green zone" in dust_hose_chunks[0].content


def test_all_four_diagnostic_steps_become_separate_atomic_chunks():
    chunks = _ingest_real_manual()
    diagnostic_chunks = [c for c in chunks if c.section_type == SectionType.DIAGNOSTIC]

    assert len(diagnostic_chunks) == 4
    assert any("overheating" in c.content for c in diagnostic_chunks)


def test_no_chunk_is_empty_and_every_chunk_has_a_source_ref():
    chunks = _ingest_real_manual()

    assert all(c.content.strip() for c in chunks)
    assert all(c.source_ref for c in chunks)
