"""The same behavioural contract, run against both real adapters with a mock
HTTP transport (no network). Any adapter added later must pass it too."""

import asyncio
import json

import httpx
import pytest

from application.ports.llm_provider import (
    Message,
    ProviderRejectedError,
    ProviderUnavailableError,
    ToolCall,
    ToolDefinition,
)
from infrastructure.llm.ollama_provider import OllamaProvider
from infrastructure.llm.openai_compatible_provider import OpenAICompatibleProvider

KEY = "sk-test-" + "x" * 24
TOOL = ToolDefinition("lookup", "look something up", {"type": "object", "properties": {}})
MESSAGES = [Message(role="user", content="hello")]


def run(coro):
    return asyncio.run(coro)


def ollama(handler) -> OllamaProvider:
    return OllamaProvider(transport=httpx.MockTransport(handler))


def openai(handler) -> OpenAICompatibleProvider:
    return OpenAICompatibleProvider(api_key=KEY, transport=httpx.MockTransport(handler))


def ollama_ok(request: httpx.Request) -> httpx.Response:
    if request.url.path == "/api/embed":
        return httpx.Response(200, json={"embeddings": [[0.1, 0.2], [0.3, 0.4]]})
    return httpx.Response(200, json={
        "model": "llama", "message": {"content": "hi there"},
        "prompt_eval_count": 7, "eval_count": 3,
    })


def openai_ok(request: httpx.Request) -> httpx.Response:
    if request.url.path.endswith("/embeddings"):
        return httpx.Response(200, json={"data": [
            {"index": 1, "embedding": [0.3, 0.4]}, {"index": 0, "embedding": [0.1, 0.2]},
        ]})
    return httpx.Response(200, json={
        "model": "gpt", "choices": [{"message": {"content": "hi there"}}],
        "usage": {"prompt_tokens": 7, "completion_tokens": 3},
    })


ADAPTERS = [("ollama", ollama, ollama_ok), ("openai", openai, openai_ok)]


@pytest.mark.parametrize("name,make,ok", ADAPTERS)
def test_complete_returns_content_and_token_usage(name, make, ok):
    result = run(make(ok).complete(MESSAGES))

    assert result.content == "hi there"
    assert (result.input_tokens, result.output_tokens) == (7, 3)
    assert result.model


@pytest.mark.parametrize("name,make,ok", ADAPTERS)
def test_embeddings_come_back_in_input_order(name, make, ok):
    assert run(make(ok).embed(["a", "b"])) == [[0.1, 0.2], [0.3, 0.4]]


@pytest.mark.parametrize("name,make", [("ollama", ollama), ("openai", openai)])
@pytest.mark.parametrize("status", [429, 500, 503, 401])
def test_availability_failures_become_provider_unavailable(name, make, status):
    provider = make(lambda request: httpx.Response(status, text="boom"))

    with pytest.raises(ProviderUnavailableError) as caught:
        run(provider.complete(MESSAGES))
    assert str(status) in str(caught.value)


@pytest.mark.parametrize("name,make", [("ollama", ollama), ("openai", openai)])
def test_a_request_the_provider_refuses_is_not_treated_as_an_outage(name, make):
    provider = make(lambda request: httpx.Response(400, text="bad request"))

    with pytest.raises(ProviderRejectedError):
        run(provider.complete(MESSAGES))


@pytest.mark.parametrize("name,make", [("ollama", ollama), ("openai", openai)])
def test_a_network_failure_becomes_provider_unavailable(name, make):
    def refuse(request):
        raise httpx.ConnectError("connection refused")

    with pytest.raises(ProviderUnavailableError):
        run(make(refuse).complete(MESSAGES))
    with pytest.raises(ProviderUnavailableError):
        run(make(refuse).embed(["a"]))


@pytest.mark.parametrize("name,make", [("ollama", ollama), ("openai", openai)])
def test_json_mode_is_requested_only_when_there_are_no_tools(name, make):
    seen = []

    def spy(request):
        seen.append(json.loads(request.content))
        return httpx.Response(200, json={
            "model": "m", "message": {"content": "{}"},
            "choices": [{"message": {"content": "{}"}}],
        })

    run(make(spy).complete(MESSAGES, json_mode=True))
    run(make(spy).complete(MESSAGES, tools=[TOOL], json_mode=True))

    with_json, with_tools = seen
    assert ("format" in with_json) or ("response_format" in with_json)
    assert "format" not in with_tools and "response_format" not in with_tools
    assert with_tools["tools"]


# --- OpenAI wire-format details ------------------------------------------------


def test_openai_tool_calls_are_parsed_and_bad_argument_json_is_flagged_not_guessed():
    def reply(request):
        return httpx.Response(200, json={"model": "gpt", "choices": [{"message": {
            "content": None,
            "tool_calls": [
                {"id": "c1", "function": {"name": "lookup", "arguments": '{"q": "spindle"}'}},
                {"id": "c2", "function": {"name": "lookup", "arguments": "{not json"}},
            ],
        }}]})

    good, bad = run(openai(reply).complete(MESSAGES, tools=[TOOL])).tool_calls

    assert good == ToolCall("c1", "lookup", {"q": "spindle"})
    assert "__unparseable_arguments__" in bad.arguments


def test_openai_mints_tool_call_ids_for_calls_that_came_from_another_provider():
    """After a failover part-way through an agent loop the history holds
    tool calls with no ids; the wire format needs matching ids."""
    seen = []

    def spy(request):
        seen.append(json.loads(request.content))
        return httpx.Response(200, json={"model": "m", "choices": [{"message": {"content": "ok"}}]})

    history = [
        Message(role="user", content="find it"),
        Message(role="assistant", content="", tool_calls=(ToolCall("", "lookup", {"q": "x"}),)),
        Message(role="tool", content="{}", name="lookup"),
    ]
    run(openai(spy).complete(history, tools=[TOOL]))

    _, assistant, tool = seen[0]["messages"]
    assert assistant["tool_calls"][0]["id"] == tool["tool_call_id"] != ""
    assert assistant["tool_calls"][0]["function"]["arguments"] == '{"q": "x"}'


def test_openai_stream_yields_tokens_then_usage_and_asks_for_it():
    seen = []
    sse = (
        'data: {"model":"gpt","choices":[{"delta":{"content":"Hel"}}]}\n\n'
        'data: {"choices":[{"delta":{"content":"lo"}}]}\n\n'
        'data: {"choices":[],"usage":{"prompt_tokens":5,"completion_tokens":2}}\n\n'
        "data: [DONE]\n\n"
    )

    def reply(request):
        seen.append(json.loads(request.content))
        return httpx.Response(200, text=sse, headers={"content-type": "text/event-stream"})

    async def collect():
        return [e async for e in openai(reply).stream(MESSAGES)]

    events = run(collect())

    assert "".join(e.text for e in events if e.kind == "token") == "Hello"
    done = events[-1]
    assert (done.kind, done.input_tokens, done.output_tokens, done.model) == ("done", 5, 2, "gpt")
    assert seen[0]["stream_options"] == {"include_usage": True}


def test_openai_stream_reassembles_a_tool_call_split_across_deltas():
    sse = (
        'data: {"choices":[{"delta":{"tool_calls":[{"index":0,"id":"c9",'
        '"function":{"name":"lookup","arguments":"{\\"q\\":"}}]}}]}\n\n'
        'data: {"choices":[{"delta":{"tool_calls":[{"index":0,'
        '"function":{"arguments":"\\"x\\"}"}}]}}]}\n\n'
        "data: [DONE]\n\n"
    )

    async def collect():
        provider = openai(lambda request: httpx.Response(200, text=sse))
        return [e async for e in provider.stream(MESSAGES, tools=[TOOL])]

    calls = [e.tool_call for e in run(collect()) if e.kind == "tool_call"]

    assert calls == [ToolCall("c9", "lookup", {"q": "x"})]


def test_the_api_key_is_sent_as_a_header_and_never_appears_in_errors_or_repr():
    seen = []

    def reply(request):
        seen.append(request.headers["authorization"])
        return httpx.Response(401, text="invalid key " + KEY)

    provider = openai(reply)
    with pytest.raises(ProviderUnavailableError) as caught:
        run(provider.complete(MESSAGES))

    assert seen == [f"Bearer {KEY}"]
    assert KEY not in str(caught.value) and KEY not in repr(provider)


def test_the_hosted_adapter_refuses_to_start_without_a_key():
    with pytest.raises(ValueError):
        OpenAICompatibleProvider(api_key="")


@pytest.mark.parametrize("name", ["ollama", "openai"])
def test_the_output_token_cap_is_sent_to_the_provider(name):
    seen = []

    def spy(request):
        seen.append(json.loads(request.content))
        return httpx.Response(200, json={
            "model": "m", "message": {"content": "x"}, "choices": [{"message": {"content": "x"}}],
        })

    transport = httpx.MockTransport(spy)
    if name == "ollama":
        provider = OllamaProvider(max_output_tokens=256, transport=transport)
    else:
        provider = OpenAICompatibleProvider(api_key=KEY, max_output_tokens=256, transport=transport)

    run(provider.complete(MESSAGES))

    capped = seen[0]["options"]["num_predict"] if name == "ollama" else seen[0]["max_tokens"]
    assert capped == 256
