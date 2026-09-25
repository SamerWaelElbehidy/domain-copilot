from __future__ import annotations

import re
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Redaction:
    text: str
    counts: dict[str, int] = field(default_factory=dict)

    @property
    def total(self) -> int:
        return sum(self.counts.values())


_EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
# Egyptian national ID: 14 digits, century digit 2 or 3.
_NATIONAL_ID = re.compile(r"(?<!\d)[23]\d{13}(?!\d)")
# Egyptian mobile, with or without the country code (010/011/012/015 prefixes).
_PHONE_EG = re.compile(r"(?<!\d)(?:\+?20[\s-]?|0)1[0125][\s-]?\d{4}[\s-]?\d{4}(?!\d)")
_PHONE_INTL = re.compile(r"(?<![\w+])\+\d{1,3}[\s-]?\d{2,4}[\s-]?\d{3,4}[\s-]?\d{3,4}(?!\d)")
_CARD_CANDIDATE = re.compile(r"(?<!\d)(?:\d[ -]?){12,18}\d(?!\d)")


def _luhn_ok(digits: str) -> bool:
    total, flip = 0, False
    for char in reversed(digits):
        n = int(char)
        if flip:
            n = n * 2 - 9 if n * 2 > 9 else n * 2
        total += n
        flip = not flip
    return total % 10 == 0


def redact_pii(text: str) -> Redaction:
    """Replaces personal identifiers with typed placeholders before text is
    stored or sent to a model (OWASP LLM: sensitive information disclosure).

    Deliberately narrow and pattern-based: emails, Egyptian national ids and
    mobile numbers, international phone numbers, and payment card numbers
    that pass the Luhn check. It does not attempt names or addresses, which
    need an NER model (see the design doc gap table), and it must leave
    technical text alone: part numbers, ratings and ranges are not matched.
    Placeholders carry the type, never any part of the value."""
    counts: dict[str, int] = {}

    def swap(pattern: re.Pattern[str], label: str, source: str, check=None) -> str:
        def replace(match: re.Match[str]) -> str:
            if check is not None and not check(match.group(0)):
                return match.group(0)
            counts[label] = counts.get(label, 0) + 1
            return f"[{label}]"

        return pattern.sub(replace, source)

    text = swap(_EMAIL, "EMAIL", text)
    text = swap(_NATIONAL_ID, "NATIONAL_ID", text)
    text = swap(_PHONE_EG, "PHONE", text)
    text = swap(_PHONE_INTL, "PHONE", text)
    text = swap(
        _CARD_CANDIDATE, "CARD", text,
        check=lambda s: 13 <= len(re.sub(r"\D", "", s)) <= 19 and _luhn_ok(re.sub(r"\D", "", s)),
    )
    return Redaction(text, counts)
