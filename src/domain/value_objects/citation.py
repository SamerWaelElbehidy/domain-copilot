from dataclasses import dataclass


@dataclass(frozen=True)
class Citation:
    """A traceable pointer from a claim back to the exact source chunk
    (FR-2: citations mandatory, structured, traceable)."""

    chunk_id: str
    document_id: str
    section_title: str
    source_ref: str
