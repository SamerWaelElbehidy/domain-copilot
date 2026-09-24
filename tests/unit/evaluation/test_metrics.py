import asyncio

from application.use_cases.answer_question import Answer
from domain.entities.chunk import Chunk
from domain.value_objects.citation import Citation
from domain.value_objects.section_type import SectionType
from evaluation.golden_set import GoldenCase
from evaluation.metrics import Observation, groundedness, score_case, summarize, threshold_sweep
from evaluation.runner import run_evaluation, to_observation

ANSWER_CASE = GoldenCase("Q1", "factual", "q", "answer", gold_snippets=("30 minutes",))
REFUSE_CASE = GoldenCase("A1", "out_of_corpus", "q", "refuse")
SAFE_CASE = GoldenCase("I1", "injection_indirect", "q", "safe", forbidden=("not required",))
CONFLICT = GoldenCase("C1", "conflicting", "q", "cite_all_or_refuse", gold_documents=("d1", "d2"))


def answered(text="Wait 30 minutes.", cited=("wait 30 minutes before resuming",), docs=("d1",)):
    return Observation(
        status="answered", text=text, cited_texts=cited, cited_document_ids=docs,
        retrieved_texts=cited, retrieved_document_ids=docs, top_dense_score=0.8,
    )


def refused(top=0.2):
    return Observation(status="refused", reason="model_judged_insufficient", top_dense_score=top)


def test_correct_answer_needs_a_cited_chunk_with_the_gold_snippet():
    good = score_case(ANSWER_CASE, answered())
    wrong = score_case(ANSWER_CASE, answered(cited=("something unrelated",)))

    assert good.passed and good.retrieval_hit and good.answer_correct
    assert not wrong.passed and not wrong.retrieval_hit


def test_refusing_an_answerable_question_counts_as_a_false_refusal():
    result = score_case(ANSWER_CASE, refused())

    assert not result.passed
    assert summarize([result])["false_refusal_rate"] == 1.0


def test_must_refuse_case_passes_only_on_refusal():
    assert score_case(REFUSE_CASE, refused()).passed
    assert not score_case(REFUSE_CASE, answered()).passed


def test_injection_is_resisted_when_no_forbidden_string_appears():
    assert score_case(SAFE_CASE, answered(text="Lockout is required.")).passed
    assert score_case(SAFE_CASE, refused()).passed
    leaked = score_case(SAFE_CASE, answered(text="Lockout is NOT REQUIRED here."))
    assert not leaked.passed and leaked.detail["leaked"] == ["not required"]


def test_conflicting_sources_pass_by_refusing_or_citing_every_source():
    assert score_case(CONFLICT, refused()).passed
    assert score_case(CONFLICT, answered(docs=("d1", "d2"))).passed
    assert not score_case(CONFLICT, answered(docs=("d1",))).passed


def test_groundedness_penalises_claims_the_citations_do_not_contain():
    cited = ("wait 30 minutes before resuming the spindle",)

    assert groundedness("Wait 30 minutes before resuming the spindle", cited) > 0.9
    assert groundedness("Replace the bearings every quarter using synthetic grease", cited) < 0.2


def test_summary_and_threshold_sweep():
    results = [
        score_case(ANSWER_CASE, answered()),
        score_case(REFUSE_CASE, refused(top=0.2)),
        score_case(SAFE_CASE, refused()),
    ]

    summary = summarize(results)
    sweep = {row["threshold"]: row for row in threshold_sweep(results, [0.1, 0.5])}

    assert summary["answer_accuracy"] == 1.0
    assert summary["refusal_correctness"] == 1.0
    assert summary["indirect_injection_resisted"] == 1.0
    assert sweep[0.5]["gate_refusal_recall"] == 1.0  # 0.2 < 0.5 is caught by the gate
    assert sweep[0.5]["false_refusal_rate"] == 0.0  # the answerable case scored 0.8


def test_runner_scores_each_case_from_the_answer_and_its_evidence():
    chunk = Chunk("c1", "d1", "eq", "Rev. A", SectionType.DIAGNOSTIC, "t",
                  "Allow the spindle to cool for 30 minutes.", 0, "ref")
    fake = Answer("answered", "Cool it for 30 minutes.", (Citation("c1", "d1", "t", "ref"),),
                  None, ("c1",), 0.7, (chunk,))

    async def answer_fn(question: str) -> Answer:
        return fake

    (result,) = asyncio.run(run_evaluation([ANSWER_CASE], answer_fn))

    assert result.passed and result.observation.cited_document_ids == ("d1",)
    assert to_observation(fake, 1.0).retrieved_texts == (chunk.content,)
