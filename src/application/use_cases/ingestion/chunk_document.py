from __future__ import annotations

import re

from domain.entities.chunk import Chunk
from domain.value_objects.section_type import SectionType

_SECTION_TYPE_BY_HEADING = {
    "overview & specifications": SectionType.OVERVIEW,
    "safety prerequisites": SectionType.SAFETY_PREREQUISITE,
    "installation & setup": SectionType.INSTALLATION,
    "operating procedures": SectionType.OPERATING,
    "maintenance schedule": SectionType.MAINTENANCE,
    "diagnostic & troubleshooting": SectionType.DIAGNOSTIC,
    "parts catalog": SectionType.PARTS,
    "revision history": SectionType.REVISION_HISTORY,
}

_HEADING_RE = re.compile(r"^##\s+(.*)$", re.MULTILINE)
_NUMBERED_ITEM_RE = re.compile(r"^\d+\.\s+", re.MULTILINE)

NARRATIVE_TARGET_CHARS = 1600  # ~400 tokens
NARRATIVE_OVERLAP_CHARS = 240  # ~15%


class UnknownSectionHeadingError(ValueError):
    """A `##` heading in the source Markdown doesn't match any known
    SectionType -- fail loudly rather than silently dropping content."""


def chunk_document(
    *,
    document_id: str,
    equipment_id: str,
    manual_revision: str,
    body: str,
) -> list[Chunk]:
    """Chunk stage (FR-1), implementing ADR-0002: atomic sections
    (safety_prerequisite, diagnostic) split one numbered item per chunk;
    narrative sections use a sliding window with overlap."""
    chunks: list[Chunk] = []
    order_index = 0

    for heading, section_body in _split_into_sections(body):
        section_type = _resolve_section_type(heading)

        if section_type.is_atomic:
            pieces = [
                (f"{heading} #{item_number}", item_text)
                for item_number, item_text in _split_numbered_items(section_body)
            ]
        else:
            pieces = [
                (f"{heading} (part {i + 1})", window_text)
                for i, window_text in enumerate(_sliding_window(section_body))
            ]

        for source_ref, content in pieces:
            chunks.append(
                Chunk(
                    chunk_id=f"{document_id}::{section_type.value}::{order_index}",
                    document_id=document_id,
                    equipment_id=equipment_id,
                    manual_revision=manual_revision,
                    section_type=section_type,
                    section_title=heading,
                    content=content,
                    order_index=order_index,
                    source_ref=source_ref,
                )
            )
            order_index += 1

    return chunks


def _resolve_section_type(heading: str) -> SectionType:
    key = heading.strip().lower()
    if key not in _SECTION_TYPE_BY_HEADING:
        raise UnknownSectionHeadingError(
            f"Unrecognized section heading '{heading}' -- add it to "
            "_SECTION_TYPE_BY_HEADING or fix the source document."
        )
    return _SECTION_TYPE_BY_HEADING[key]


def _split_into_sections(body: str) -> list[tuple[str, str]]:
    headings = list(_HEADING_RE.finditer(body))
    sections: list[tuple[str, str]] = []
    for i, match in enumerate(headings):
        heading = match.group(1).strip()
        start = match.end()
        end = headings[i + 1].start() if i + 1 < len(headings) else len(body)
        sections.append((heading, body[start:end].strip()))
    return sections


def _split_numbered_items(section_body: str) -> list[tuple[int, str]]:
    starts = list(_NUMBERED_ITEM_RE.finditer(section_body))
    items: list[tuple[int, str]] = []
    for i, match in enumerate(starts):
        start = match.start()
        end = starts[i + 1].start() if i + 1 < len(starts) else len(section_body)
        items.append((i + 1, section_body[start:end].strip()))
    return items


def _sliding_window(
    text: str,
    target_chars: int = NARRATIVE_TARGET_CHARS,
    overlap_chars: int = NARRATIVE_OVERLAP_CHARS,
) -> list[str]:
    if not text:
        return []
    if len(text) <= target_chars:
        return [text]

    windows: list[str] = []
    start = 0
    while start < len(text):
        end = min(start + target_chars, len(text))
        windows.append(text[start:end].strip())
        if end == len(text):
            break
        start = end - overlap_chars
    return windows
