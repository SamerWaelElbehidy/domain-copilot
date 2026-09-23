from pathlib import Path

import pytest

from application.use_cases.ingest_document import ingest_markdown_document

CORPUS_ROOT = Path(__file__).resolve().parents[2] / "corpus"
MANUAL_PATHS = sorted(CORPUS_ROOT.rglob("*.md"))


@pytest.mark.parametrize(
    "manual_path",
    MANUAL_PATHS,
    ids=[p.relative_to(CORPUS_ROOT).as_posix() for p in MANUAL_PATHS],
)
def test_every_corpus_document_ingests_cleanly(manual_path: Path):
    raw_text = manual_path.read_text(encoding="utf-8")

    chunks = ingest_markdown_document(raw_text)

    assert len(chunks) > 0, f"{manual_path} produced no chunks"
    assert all(c.content.strip() for c in chunks), f"{manual_path} has an empty chunk"
    assert all(c.equipment_id for c in chunks)
    assert all(c.document_id for c in chunks)
    assert all(c.manual_revision for c in chunks)
    assert all(c.source_ref for c in chunks)


def test_corpus_document_count_progress():
    """Tracks progress toward the brief's >=30 document floor -- not
    meant to pass yet; raises the bar as documents land."""
    print(f"\nCorpus documents so far: {len(MANUAL_PATHS)} / 30 target")
    assert len(MANUAL_PATHS) >= 1
