from enum import Enum


class SectionType(str, Enum):
    """Matches the manual structure fixed in ADR-0002. `SAFETY_PREREQUISITE`
    and `DIAGNOSTIC` chunks are never split/merged across boundaries —
    everything else uses a normal sliding-window chunker."""

    OVERVIEW = "overview"
    SAFETY_PREREQUISITE = "safety_prerequisite"
    INSTALLATION = "installation"
    OPERATING = "operating"
    MAINTENANCE = "maintenance"
    DIAGNOSTIC = "diagnostic"
    PARTS = "parts"
    REVISION_HISTORY = "revision_history"

    @property
    def is_atomic(self) -> bool:
        """Atomic sections are chunked one-item-per-chunk (ADR-0002)."""
        return self in (SectionType.SAFETY_PREREQUISITE, SectionType.DIAGNOSTIC)
