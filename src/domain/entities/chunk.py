from dataclasses import dataclass

from domain.value_objects.section_type import SectionType


@dataclass(frozen=True)
class Chunk:
    chunk_id: str
    document_id: str
    equipment_id: str
    manual_revision: str
    section_type: SectionType
    section_title: str
    content: str
    order_index: int
    source_ref: str
