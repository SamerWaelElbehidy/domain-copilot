import asyncio

import pytest

from application.llm_fallback import FallbackLLMProvider
from application.ports.llm_provider import (
    CompletionResult,
    LLMProvider,
    Message,
    ProviderRejectedError,
    ProviderUnavailableError,
    StreamEvent,
)

MESSAGES = [Message(role="user", content="hi")]


def run(coro):
    return asyncio.run(coro)


class Scripted(LLMProvider):
    """Fails while `down` is set; otherwise answers with its own name."""

    def __init__(self, name: str, down: bool = False, fail_after_tokens: int | None = None):
        self.name, self.down, self.fail_after = name, down, fail_after_tokens
        self.calls = 0
        self.embeds = 0

    async def complete(self, messages, tools=None, json_mode=False):
        self.calls += 1
        if self.down:
            raise ProviderUnavailableError(f"{self.name}: down")
        return CompletionResult(content=self.name, model=f"{self.name}-model")

    async def stream(self, messages, tools=None, json_mode=False):
        self.calls += 1
        if self.down and self.fail_after is None:
            raise ProviderUnavailableError(f"{self.name}: down")
        for i, word in enumerate(["a", "b", "c"]):
            if self.fail_after is not None and i == self.fail_after:
                raise ProviderUnavailableError(f"{self.name}: dropped mid-stream")
            yield StreamEvent(kind="token", text=word)
        yield StreamEvent(kind="done", model=f"{self.name}-model")

    async def embed(self, texts):
        self.embeds += 1
        if self.down:
            raise ProviderUnavailableError(f"{self.name}: down")
        return [[1.0] for _ in texts]


class Clock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now


def chain(*providers, **kwargs) -> FallbackLLMProvider:
    return FallbackLLMProvider([(p.name, p) for p in providers], **kwargs)


def test_the_first_healthy_provider_serves_and_is_named_on_the_result():
    a, b = Scripted("a"), Scripted("b")

    result = run(chain(a, b).complete(MESSAGES))

    assert (result.content, result.provider) == ("a", "a")
    assert b.calls == 0


def test_it_fails_over_when_the_preferred_provider_is_unavailable():
    a, b = Scripted("a", down=True), Scripted("b")

    result = run(chain(a, b).complete(MESSAGES))

    assert (result.content, result.provider) == ("b", "b")


def test_when_every_provider_is_down_the_error_is_retryable_and_lists_each_cause():
    with pytest.raises(ProviderUnavailableError) as caught:
        run(chain(Scripted("a", down=True), Scripted("b", down=True)).complete(MESSAGES))

    assert "a: down" in str(caught.value) and "b: down" in str(caught.value)
    assert isinstance(caught.value, ConnectionError)  # the orchestrator's retry policy


def test_a_rejected_request_is_not_failed_over():
    class Rejecting(Scripted):
        async def complete(self, messages, tools=None, json_mode=False):
            raise ProviderRejectedError("a: HTTP 400")

    b = Scripted("b")

    with pytest.raises(ProviderRejectedError):
        run(chain(Rejecting("a"), b).complete(MESSAGES))
    assert b.calls == 0


def test_a_repeatedly_failing_provider_is_skipped_until_its_cooldown_ends():
    clock = Clock()
    a, b = Scripted("a", down=True), Scripted("b")
    llm = chain(a, b, failure_threshold=2, cooldown_seconds=30, clock=clock)

    for _ in range(4):
        run(llm.complete(MESSAGES))
    assert a.calls == 2 and llm.status() == {"a": "open", "b": "closed"}

    clock.now = 31
    a.down = False
    result = run(llm.complete(MESSAGES))

    assert result.provider == "a" and a.calls == 3


def test_a_success_resets_the_failure_count():
    clock = Clock()
    a, b = Scripted("a", down=True), Scripted("b")
    llm = chain(a, b, failure_threshold=2, clock=clock)

    run(llm.complete(MESSAGES))  # a fails once
    a.down = False
    run(llm.complete(MESSAGES))  # a succeeds, count resets
    a.down = True
    run(llm.complete(MESSAGES))  # a fails once more, still below the threshold

    assert llm.status()["a"] == "closed"


def test_if_every_breaker_is_open_it_still_tries_rather_than_giving_up():
    clock = Clock()
    a, b = Scripted("a", down=True), Scripted("b", down=True)
    llm = chain(a, b, failure_threshold=1, cooldown_seconds=60, clock=clock)
    with pytest.raises(ProviderUnavailableError):
        run(llm.complete(MESSAGES))
    a.down = False

    assert run(llm.complete(MESSAGES)).provider == "a"


def collect(llm):
    async def go():
        return [e async for e in llm.stream(MESSAGES)]

    return run(go())


def test_streaming_fails_over_before_the_first_token():
    events = collect(chain(Scripted("a", down=True), Scripted("b")))

    assert "".join(e.text for e in events if e.kind == "token") == "abc"
    assert {e.provider for e in events} == {"b"}


def test_a_mid_stream_failure_is_raised_not_spliced_onto_another_model():
    b = Scripted("b")

    with pytest.raises(ProviderUnavailableError):
        collect(chain(Scripted("a", fail_after_tokens=1), b))
    assert b.calls == 0


def test_embeddings_never_fail_over_because_vector_spaces_differ():
    a, b = Scripted("a", down=True), Scripted("b")

    with pytest.raises(ProviderUnavailableError):
        run(chain(a, b).embed(["x"]))
    assert b.embeds == 0


def test_the_embedding_provider_can_differ_from_the_preferred_chat_provider():
    a, b = Scripted("a"), Scripted("b")

    run(chain(a, b, embedding_provider="b").embed(["x"]))

    assert (a.embeds, b.embeds) == (0, 1)


@pytest.mark.parametrize("kwargs", [{"embedding_provider": "nope"}])
def test_configuration_errors_fail_at_construction(kwargs):
    with pytest.raises(ValueError):
        chain(Scripted("a"), **kwargs)
    with pytest.raises(ValueError):
        FallbackLLMProvider([])
    with pytest.raises(ValueError):
        chain(Scripted("a"), Scripted("a"))
