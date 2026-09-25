from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any

import httpx

from application.ports.llm_provider import (
    CompletionResult,
    LLMProvider,
    Message,
    StreamEvent,
    ToolCall,
    ToolDefinition,
)
from infrastructure.llm.http_errors import translate


class OpenAICompatibleProvider(LLMProvider):
    """Hosted LLMProvider adapter for the OpenAI chat-completions protocol,
    which OpenAI and many free-tier hosts (Groq, OpenRouter, Gemini's
    compatibility endpoint, a local vLLM) all speak. Selecting a different
    host is a base URL and a key, never a code change (ADR-0007).

    The API key is held only to build the Authorization header. It is never
    logged, never put in an error message, and never written anywhere."""

    def __init__(
        self,
        api_key: str,
        base_url: str = "https://api.openai.com/v1",
        chat_model: str = "gpt-4o-mini",
        embed_model: str = "text-embedding-3-small",
        embed_dimensions: int | None = None,
        timeout_seconds: float = 60.0,
        temperature: float = 0.0,
        seed: int | None = 42,
        name: str = "openai",
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        if not api_key:
            raise ValueError("an API key is required for the hosted provider")
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._chat_model = chat_model
        self._embed_model = embed_model
        self._embed_dimensions = embed_dimensions
        self._timeout = timeout_seconds
        self._temperature = temperature
        self._seed = seed
        self._name = name
        self._transport = transport

    def __repr__(self) -> str:  # keep the key out of logs and tracebacks
        return f"OpenAICompatibleProvider(name={self._name!r}, model={self._chat_model!r})"

    def _client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            timeout=self._timeout,
            transport=self._transport,
            headers={"Authorization": f"Bearer {self._api_key}"},
        )

    async def complete(
        self,
        messages: list[Message],
        tools: list[ToolDefinition] | None = None,
        json_mode: bool = False,
    ) -> CompletionResult:
        payload = self._payload(messages, tools, json_mode, stream=False)
        try:
            async with self._client() as client:
                response = await client.post(f"{self._base_url}/chat/completions", json=payload)
                response.raise_for_status()
                return _parse_completion(response.json())
        except httpx.HTTPError as exc:
            raise translate(exc, self._name) from None

    async def stream(
        self,
        messages: list[Message],
        tools: list[ToolDefinition] | None = None,
        json_mode: bool = False,
    ) -> AsyncIterator[StreamEvent]:
        payload = self._payload(messages, tools, json_mode, stream=True)
        payload["stream_options"] = {"include_usage": True}
        partial_calls: dict[int, dict[str, str]] = {}
        usage: dict[str, Any] = {}
        model = ""
        try:
            async with self._client() as client:
                async with client.stream(
                    "POST", f"{self._base_url}/chat/completions", json=payload
                ) as response:
                    response.raise_for_status()
                    async for line in response.aiter_lines():
                        if not line.startswith("data:"):
                            continue
                        data = line[5:].strip()
                        if data == "[DONE]":
                            break
                        chunk = json.loads(data)
                        model = chunk.get("model") or model
                        usage = chunk.get("usage") or usage
                        for choice in chunk.get("choices", []):
                            delta = choice.get("delta", {})
                            if delta.get("content"):
                                yield StreamEvent(kind="token", text=delta["content"])
                            for part in delta.get("tool_calls", []) or []:
                                slot = partial_calls.setdefault(
                                    part.get("index", 0), {"id": "", "name": "", "arguments": ""}
                                )
                                slot["id"] = part.get("id") or slot["id"]
                                function = part.get("function", {})
                                slot["name"] = function.get("name") or slot["name"]
                                slot["arguments"] += function.get("arguments") or ""
        except httpx.HTTPError as exc:
            raise translate(exc, self._name) from None
        for index in sorted(partial_calls):
            call = partial_calls[index]
            yield StreamEvent(
                kind="tool_call",
                tool_call=ToolCall(call["id"], call["name"], _parse_arguments(call["arguments"])),
            )
        yield StreamEvent(
            kind="done",
            input_tokens=usage.get("prompt_tokens", 0),
            output_tokens=usage.get("completion_tokens", 0),
            model=model,
        )

    async def embed(self, texts: list[str]) -> list[list[float]]:
        payload: dict[str, Any] = {"model": self._embed_model, "input": texts}
        if self._embed_dimensions:
            payload["dimensions"] = self._embed_dimensions
        try:
            async with self._client() as client:
                response = await client.post(f"{self._base_url}/embeddings", json=payload)
                response.raise_for_status()
                rows = sorted(response.json()["data"], key=lambda r: r["index"])
                return [row["embedding"] for row in rows]
        except httpx.HTTPError as exc:
            raise translate(exc, self._name) from None

    def _payload(
        self,
        messages: list[Message],
        tools: list[ToolDefinition] | None,
        json_mode: bool,
        stream: bool,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": self._chat_model,
            "messages": _messages_to_wire(messages),
            "temperature": self._temperature,
            "stream": stream,
        }
        if self._seed is not None:
            payload["seed"] = self._seed
        if tools:
            payload["tools"] = [
                {
                    "type": "function",
                    "function": {
                        "name": t.name,
                        "description": t.description,
                        "parameters": t.parameters,
                    },
                }
                for t in tools
            ]
        elif json_mode:
            payload["response_format"] = {"type": "json_object"}
        return payload


def _messages_to_wire(messages: list[Message]) -> list[dict[str, Any]]:
    """The wire format needs an id on every tool call and a matching id on its
    result. Calls that came from another provider (after a failover part-way
    through an agent loop) may have none, so ids are minted and paired by
    order."""
    wire: list[dict[str, Any]] = []
    pending: list[str] = []
    minted = 0
    for message in messages:
        if message.role == "assistant" and message.tool_calls:
            calls = []
            for call in message.tool_calls:
                call_id = call.id
                if not call_id:
                    minted += 1
                    call_id = f"call_{minted}"
                    pending.append(call_id)
                calls.append(
                    {
                        "id": call_id,
                        "type": "function",
                        "function": {"name": call.name, "arguments": json.dumps(call.arguments)},
                    }
                )
            wire.append(
                {"role": "assistant", "content": message.content or None, "tool_calls": calls}
            )
        elif message.role == "tool":
            call_id = message.tool_call_id or (pending.pop(0) if pending else "call_0")
            wire.append({"role": "tool", "tool_call_id": call_id, "content": message.content})
        else:
            wire.append({"role": message.role, "content": message.content})
    return wire


def _parse_arguments(raw: str) -> dict[str, Any]:
    """Models sometimes emit broken JSON for arguments. Passing it through as
    an unexpected key makes the tool registry reject the call, and the model is
    told why, instead of the adapter guessing what was meant."""
    if not raw.strip():
        return {}
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return {"__unparseable_arguments__": raw[:200]}
    return parsed if isinstance(parsed, dict) else {"__unparseable_arguments__": raw[:200]}


def _parse_completion(data: dict[str, Any]) -> CompletionResult:
    message = data["choices"][0]["message"]
    calls = [
        ToolCall(
            id=c.get("id", ""),
            name=c["function"]["name"],
            arguments=_parse_arguments(c["function"].get("arguments", "")),
        )
        for c in message.get("tool_calls") or []
    ]
    usage = data.get("usage") or {}
    return CompletionResult(
        content=message.get("content") or "",
        tool_calls=calls,
        input_tokens=usage.get("prompt_tokens", 0),
        output_tokens=usage.get("completion_tokens", 0),
        model=data.get("model", ""),
    )
