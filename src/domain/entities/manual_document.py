from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class ManualDocument:
    """One revision of one equipment manual. `revision` is what the
    Symptom Matcher agent must resolve alongside the equipment itself —
    retrieval has to be revision-aware, not just equipment-aware."""

    document_id: str
    equipment_id: str
    revision: str
    effective_date: date
    title: str
