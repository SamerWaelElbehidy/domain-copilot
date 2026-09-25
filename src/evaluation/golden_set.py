from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

EXPECTATIONS = {"answer", "refuse", "safe", "cite_all_or_refuse"}
ADVERSARIAL_CATEGORIES = {
    "out_of_corpus",
    "ambiguous",
    "injection_direct",
    "injection_indirect",
    "conflicting",
}


@dataclass(frozen=True)
class GoldenCase:
    id: str
    category: str
    question: str
    expect: str
    gold_snippets: tuple[str, ...] = ()
    gold_documents: tuple[str, ...] = ()
    forbidden: tuple[str, ...] = ()
    notes: str = ""

    @property
    def is_adversarial(self) -> bool:
        return self.category in ADVERSARIAL_CATEGORIES


def load_golden_set(path: Path) -> list[GoldenCase]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    cases = [
        GoldenCase(
            id=c["id"],
            category=c["category"],
            question=c["question"],
            expect=c["expect"],
            gold_snippets=tuple(s.lower() for s in c.get("gold_snippets", [])),
            gold_documents=tuple(c.get("gold_documents", [])),
            forbidden=tuple(s.lower() for s in c.get("forbidden", [])),
            notes=c.get("notes", ""),
        )
        for c in raw["cases"]
    ]
    problems = validate_golden_set(cases)
    if problems:
        raise ValueError("invalid golden set: " + "; ".join(problems))
    return cases


def validate_golden_set(cases: list[GoldenCase]) -> list[str]:
    """Checks the golden set against the brief's FR-3 floor (>=25 cases,
    >=5 adversarial, >=3 injection with an indirect one) plus basic sanity."""
    problems: list[str] = []
    ids = [c.id for c in cases]
    if len(set(ids)) != len(ids):
        problems.append("duplicate case ids")
    for case in cases:
        if case.expect not in EXPECTATIONS:
            problems.append(f"{case.id}: unknown expect '{case.expect}'")
        if case.expect == "answer" and not case.gold_snippets:
            problems.append(f"{case.id}: expect=answer needs gold_snippets")
        if case.expect == "safe" and not case.forbidden:
            problems.append(f"{case.id}: expect=safe needs forbidden strings")
        if case.expect == "cite_all_or_refuse" and len(case.gold_documents) < 2:
            problems.append(f"{case.id}: conflicting case needs >=2 gold_documents")
    if len(cases) < 25:
        problems.append(f"only {len(cases)} cases, need >=25")
    if sum(c.is_adversarial for c in cases) < 5:
        problems.append("need >=5 adversarial cases")
    injection = [c for c in cases if c.category.startswith("injection")]
    if len(injection) < 3:
        problems.append("need >=3 injection cases")
    if not any(c.category == "injection_indirect" for c in injection):
        problems.append("need at least one indirect injection case")
    return problems
