import pytest

from application.use_cases.ingestion.chunk_document import (
    UnknownSectionHeadingError,
    chunk_document,
)
from domain.value_objects.section_type import SectionType


def test_safety_section_produces_one_atomic_chunk_per_numbered_item():
    body = (
        "## Safety Prerequisites\n\n"
        "1. Lock out power before opening the enclosure.\n\n"
        "2. Wear hearing protection at all times.\n\n"
        "3. Confirm dust extraction is running before starting the spindle.\n"
    )

    chunks = chunk_document(
        document_id="doc-1", equipment_id="eq-1", manual_revision="Rev. A", body=body
    )

    assert len(chunks) == 3
    assert all(c.section_type == SectionType.SAFETY_PREREQUISITE for c in chunks)
    assert "Lock out power" in chunks[0].content
    assert "Wear hearing protection" in chunks[1].content
    assert "dust extraction" in chunks[2].content


def test_safety_item_spanning_multiple_lines_stays_in_one_chunk():
    body = (
        "## Safety Prerequisites\n\n"
        "1. Confirm the emergency stop is unobstructed and tested (press\n"
        "   and release) before every shift start.\n\n"
        "2. Wear hearing protection.\n"
    )

    chunks = chunk_document(
        document_id="doc-1", equipment_id="eq-1", manual_revision="Rev. A", body=body
    )

    assert len(chunks) == 2
    assert "press" in chunks[0].content and "and release" in chunks[0].content


def test_narrative_section_under_target_size_is_one_chunk():
    body = "## Overview & Specifications\n\nA short overview paragraph.\n"

    chunks = chunk_document(
        document_id="doc-1", equipment_id="eq-1", manual_revision="Rev. A", body=body
    )

    assert len(chunks) == 1
    assert chunks[0].section_type == SectionType.OVERVIEW


def test_narrative_section_over_target_size_is_split_with_overlap():
    long_paragraph = "word " * 500  # well over the 1600-char narrative target
    body = f"## Installation & Setup\n\n{long_paragraph}\n"

    chunks = chunk_document(
        document_id="doc-1", equipment_id="eq-1", manual_revision="Rev. A", body=body
    )

    assert len(chunks) > 1
    assert all(c.section_type == SectionType.INSTALLATION for c in chunks)
    # consecutive windows overlap: the tail of chunk N appears in chunk N+1
    tail_of_first = chunks[0].content[-100:]
    assert tail_of_first[:20] in chunks[1].content


def test_chunk_metadata_is_attached_correctly():
    body = "## Overview & Specifications\n\nSome text.\n"

    chunks = chunk_document(
        document_id="doc-cnc-1",
        equipment_id="eq-cnc-1",
        manual_revision="Rev. C",
        body=body,
    )

    chunk = chunks[0]
    assert chunk.document_id == "doc-cnc-1"
    assert chunk.equipment_id == "eq-cnc-1"
    assert chunk.manual_revision == "Rev. C"
    assert chunk.section_title == "Overview & Specifications"


def test_unrecognized_heading_raises_instead_of_silently_dropping_content():
    body = "## Some Unplanned Section\n\nContent nobody classified.\n"

    with pytest.raises(UnknownSectionHeadingError):
        chunk_document(
            document_id="doc-1", equipment_id="eq-1", manual_revision="Rev. A", body=body
        )
