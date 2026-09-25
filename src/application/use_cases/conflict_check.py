from __future__ import annotations

import re
from dataclasses import dataclass

from application.use_cases.grounding import content_tokens
from domain.entities.chunk import Chunk

_NUMBER_UNIT = re.compile(
    r"(?<![\w.])(?P<value>\d+(?:\.\d+)?)\s?(?P<unit>m/s|mm|cm|km|meters?|metres?|°c|c|"
    r"minutes?|mins?|seconds?|secs?|hours?|hrs?|days?|weeks?|months?|bar|kpa|psi|"
    r"tonnes?|kg|liters?|litres?|rpm|hz|kw|db|%)(?![\w/])",
    re.IGNORECASE,
)
_UNIT_ALIASES = {
    "°c": "c", "metre": "m", "metres": "m", "meter": "m", "meters": "m",
    "minute": "min", "minutes": "min", "mins": "min",
    "second": "s", "seconds": "s", "sec": "s", "secs": "s",
    "hour": "h", "hours": "h", "hr": "h", "hrs": "h",
    "day": "d", "days": "d", "week": "w", "weeks": "w", "month": "mo", "months": "mo",
    "tonne": "t", "tonnes": "t", "liter": "l", "liters": "l", "litre": "l", "litres": "l",
}
FACILITY_WIDE = "eq-facility-general"
_CONTEXT_WORDS = 6
_MIN_SHARED_CONTEXT = 3


@dataclass(frozen=True)
class Measurement:
    value: float
    unit: str
    raw: str
    context: frozenset[str]


@dataclass(frozen=True)
class Conflict:
    unit: str
    answered: str
    answered_document: str
    other: str
    other_document: str

    def describe(self) -> str:
        return (
            f"Sources disagree: {self.answered} ({self.answered_document}) versus "
            f"{self.other} ({self.other_document}). Check with a supervisor before acting."
        )


def _same_subject(a: Chunk, b: Chunk) -> bool:
    """Values for different machines are different facts. A facility-wide
    policy is compared with everything, since it can contradict any manual."""
    return (
        a.equipment_id == b.equipment_id
        or FACILITY_WIDE in (a.equipment_id, b.equipment_id)
    )


def measurements(text: str) -> list[Measurement]:
    found: list[Measurement] = []
    for match in _NUMBER_UNIT.finditer(text):
        unit = match.group("unit").lower()
        before = text[: match.start()].split()[-_CONTEXT_WORDS:]
        after = text[match.end() :].split()[:_CONTEXT_WORDS]
        found.append(
            Measurement(
                value=float(match.group("value")),
                unit=_UNIT_ALIASES.get(unit, unit),
                raw=match.group(0).strip(),
                context=frozenset(content_tokens(" ".join([*before, *after]))),
            )
        )
    return found


def find_conflict(
    *, answer_text: str, cited: list[Chunk], others: list[Chunk]
) -> Conflict | None:
    """Flags an answer whose numeric claim is contradicted by another
    retrieved document about the same parameter.

    A conflict needs all of: the value appears in the answer and in a cited
    chunk; another chunk from a *different document* states a value in the
    same unit; the text around the two numbers shares at least three content
    words (so "30 seconds after isolation" is not compared with "10 seconds
    before starting"); and the values differ. Qualitative contradictions
    ("required" vs "optional") are out of scope and listed as a known gap."""
    answer_values = {(m.value, m.unit) for m in measurements(answer_text)}
    if not answer_values:
        return None
    for chunk in cited:
        for claimed in measurements(chunk.content):
            if (claimed.value, claimed.unit) not in answer_values:
                continue
            for other in others:
                if other.document_id == chunk.document_id:
                    continue
                if not _same_subject(chunk, other):
                    continue
                for candidate in measurements(other.content):
                    if candidate.unit != claimed.unit or candidate.value == claimed.value:
                        continue
                    if len(claimed.context & candidate.context) >= _MIN_SHARED_CONTEXT:
                        return Conflict(
                            unit=claimed.unit,
                            answered=claimed.raw,
                            answered_document=chunk.document_id,
                            other=candidate.raw,
                            other_document=other.document_id,
                        )
    return None
