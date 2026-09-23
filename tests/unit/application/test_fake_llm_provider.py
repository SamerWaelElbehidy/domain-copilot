import asyncio

from application.ports.llm_provider import CompletionResult, LLMProvider, Message
from tests.fakes.fake_llm_provider import FakeLLMProvider


def test_fake_llm_provider_satisfies_the_port():
    assert isinstance(FakeLLMProvider(), LLMProvider)


def test_complete_returns_configured_response_and_records_messages():
    provider = FakeLLMProvider(responses=[CompletionResult(content="hello", model="fake")])
    messages = [Message(role="user", content="hi")]

    result = asyncio.run(provider.complete(messages))

    assert result.content == "hello"
    assert provider.received_messages == [messages]


def test_stream_yields_tokens_then_done():
    provider = FakeLLMProvider(responses=[CompletionResult(content="a b", model="fake")])

    async def collect():
        return [event async for event in provider.stream([Message(role="user", content="hi")])]

    events = asyncio.run(collect())

    assert [e.kind for e in events] == ["token", "token", "done"]


def test_embed_returns_one_vector_per_text_with_configured_dimension():
    provider = FakeLLMProvider(embedding_dim=4)

    vectors = asyncio.run(provider.embed(["a", "bb"]))

    assert len(vectors) == 2
    assert all(len(v) == 4 for v in vectors)
