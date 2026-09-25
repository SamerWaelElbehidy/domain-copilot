import asyncio
from datetime import UTC, datetime

import pytest

from application.correlation import (
    UsageContext,
    reset_correlation_id,
    reset_usage_context,
    set_correlation_id,
    set_usage_context,
)
from application.llm_recording import RecordingLLMProvider, estimate_cost
from application.ports.llm_provider import CompletionResult, Message
from tests.fakes.fake_llm_provider import FakeLLMProvider
from tests.fakes.in_memory import InMemoryLLMCallRepository

NOW = datetime(2026, 1, 1, tzinfo=UTC)
PRICES = {"hosted-model": (0.5, 1.5)}  # USD per 1k in / out, illustrative


def run(coro):
    return asyncio.run(coro)


def make(responses=None):
    inner = FakeLLMProvider(responses=responses or [])
    repo = InMemoryLLMCallRepository()
    return inner, repo, RecordingLLMProvider(inner, repo, "fake", PRICES, clock=lambda: NOW)


def with_context(coro_fn):
    async def wrapper():
        c = set_correlation_id("corr-12345678")
        u = set_usage_context(UsageContext("user-1", "run-9", "ask"))
        try:
            return await coro_fn()
        finally:
            reset_usage_context(u)
            reset_correlation_id(c)

    return run(wrapper())


def test_a_completion_is_recorded_with_tokens_cost_and_attribution():
    _, repo, llm = make([CompletionResult("hi", input_tokens=2000, output_tokens=1000,
                                          model="hosted-model")])

    with_context(lambda: llm.complete([Message("user", "q")]))

    (call,) = repo.calls
    assert (call.correlation_id, call.user_id, call.run_id, call.purpose) == (
        "corr-12345678", "user-1", "run-9", "ask")
    assert (call.operation, call.status, call.model) == ("complete", "ok", "hosted-model")
    assert (call.input_tokens, call.output_tokens) == (2000, 1000)
    assert call.cost_usd == pytest.approx(2.5)  # 2 x 0.5 + 1 x 1.5


def test_local_models_cost_nothing():
    assert estimate_cost(PRICES, "llama3.2:1b", 5000, 5000) == 0.0


def test_a_failing_call_is_recorded_as_an_error_and_still_raises():
    class Boom(FakeLLMProvider):
        async def complete(self, messages, tools=None, json_mode=False):
            raise ConnectionError("down")

    repo = InMemoryLLMCallRepository()
    llm = RecordingLLMProvider(Boom(), repo, "fake")

    with pytest.raises(ConnectionError):
        run(llm.complete([Message("user", "q")]))

    assert repo.calls[0].status == "error"


def test_a_completed_stream_records_usage_from_the_final_event():
    _, repo, llm = make([CompletionResult("one two three", input_tokens=10, output_tokens=3,
                                          model="hosted-model")])

    async def consume():
        return [e async for e in llm.stream([Message("user", "q")])]

    events = with_context(consume)

    assert [e.kind for e in events] == ["token", "token", "token", "done"]
    (call,) = repo.calls
    assert (call.operation, call.status, call.input_tokens, call.output_tokens) == (
        "stream", "ok", 10, 3)


def test_abandoning_a_stream_closes_the_provider_and_records_it_as_cancelled():
    inner, repo, llm = make([CompletionResult("a b c d e f g", model="hosted-model")])

    async def abandon_after_two_tokens():
        stream = llm.stream([Message("user", "q")])
        seen = 0
        async for _ in stream:
            seen += 1
            if seen == 2:
                break
        await stream.aclose()

    with_context(abandon_after_two_tokens)

    assert inner.stream_closed_early is True and inner.streams_finished == 1
    (call,) = repo.calls
    assert call.status == "cancelled" and call.output_tokens == 0


def test_embeddings_are_recorded_with_an_estimated_input_size():
    _, repo, llm = make()

    run(llm.embed(["x" * 400, "y" * 400]))

    assert repo.calls[0].operation == "embed" and repo.calls[0].input_tokens == 200
