from pathlib import Path

import pytest

from evaluation.golden_set import GoldenCase, load_golden_set, validate_golden_set
from infrastructure.corpus.loader import load_corpus

ROOT = Path(__file__).resolve().parents[3]
GOLDEN = ROOT / "eval" / "golden_set.json"


@pytest.fixture(scope="module")
def cases():
    return load_golden_set(GOLDEN)


@pytest.fixture(scope="module")
def corpus_text():
    items = load_corpus(ROOT / "corpus") + load_corpus(ROOT / "eval" / "extra_corpus")
    return {i.document.document_id: i.raw_text.lower() for i in items}


def test_golden_set_meets_the_fr3_floor(cases):
    assert len(cases) >= 25
    assert sum(c.is_adversarial for c in cases) >= 5
    injection = [c for c in cases if c.category.startswith("injection")]
    assert len(injection) >= 3
    assert any(c.category == "injection_indirect" for c in injection)


def test_every_gold_document_exists_in_the_corpus(cases, corpus_text):
    for case in cases:
        for document_id in case.gold_documents:
            assert document_id in corpus_text, f"{case.id}: unknown gold document {document_id}"


def test_every_answerable_case_has_a_gold_snippet_present_in_its_gold_documents(cases, corpus_text):
    for case in cases:
        if case.expect != "answer":
            continue
        haystack = " ".join(corpus_text[d] for d in case.gold_documents)
        assert any(s in haystack for s in case.gold_snippets), (
            f"{case.id}: none of {case.gold_snippets} appear in {case.gold_documents}"
        )


def test_extra_documents_are_marked_as_adversarial_fixtures():
    for path in (ROOT / "eval" / "extra_corpus").glob("*.md"):
        assert "TEST FIXTURE" in path.read_text(encoding="utf-8")


def test_validation_reports_a_too_small_set():
    problems = validate_golden_set([GoldenCase("X1", "factual", "q", "answer", ("a",))])

    assert any("need >=25" in p for p in problems)
    assert any("adversarial" in p for p in problems)
    assert any("indirect" in p for p in problems)


def test_validation_rejects_an_answerable_case_without_snippets():
    problems = validate_golden_set([GoldenCase("X1", "factual", "q", "answer")])

    assert any("needs gold_snippets" in p for p in problems)
