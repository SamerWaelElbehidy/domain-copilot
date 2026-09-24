from __future__ import annotations

import time
from collections.abc import Awaitable, Callable

from application.use_cases.answer_question import Answer
from evaluation.golden_set import GoldenCase
from evaluation.metrics import CaseResult, Observation, score_case

AnswerFn = Callable[[str], Awaitable[Answer]]


def to_observation(answer: Answer, latency_seconds: float) -> Observation:
    by_id = {c.chunk_id: c for c in answer.evidence}
    cited = [by_id[c.chunk_id] for c in answer.citations if c.chunk_id in by_id]
    return Observation(
        status=answer.status,
        text=answer.text,
        reason=answer.reason,
        cited_document_ids=tuple(dict.fromkeys(c.document_id for c in cited)),
        cited_texts=tuple(c.content for c in cited),
        retrieved_document_ids=tuple(dict.fromkeys(c.document_id for c in answer.evidence)),
        retrieved_texts=tuple(c.content for c in answer.evidence),
        top_dense_score=answer.top_dense_score,
        latency_seconds=latency_seconds,
        input_tokens=answer.input_tokens,
        output_tokens=answer.output_tokens,
    )


async def run_evaluation(
    cases: list[GoldenCase],
    answer_fn: AnswerFn,
    on_result: Callable[[CaseResult], None] | None = None,
) -> list[CaseResult]:
    results: list[CaseResult] = []
    for case in cases:
        started = time.perf_counter()
        answer = await answer_fn(case.question)
        result = score_case(case, to_observation(answer, time.perf_counter() - started))
        results.append(result)
        if on_result:
            on_result(result)
    return results
