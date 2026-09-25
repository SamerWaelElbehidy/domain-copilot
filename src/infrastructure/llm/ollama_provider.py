from __future__ import annotations

import json
from collections.abc import AsyncIterator

import httpx

from application.ports.llm_provider import (
    CompletionResult,
    LLMProvider,
    Message,
    StreamEvent,
    ToolCall,
    ToolDefinition,
)


class OllamaProvider(LLMProvider):
    """Local, free LLMProvider adapter (ADR-0003) -- talks to a local
    Ollama server over plain HTTP. No API key, no cost, works offline;
    this is why development and tests never need a hosted key."""

    def __init__(
        self,
        base_url: str = "http://localhost:11434",
        chat_model: str = "llama3.2:1b",
        embed_model: str = "nomic-embed-text",
        timeout_seconds: float = 60.0,
        temperature: float = 0.0,
        seed: int | None = 42,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._chat_model = chat_model
        self._embed_model = embed_model
        self._timeout = timeout_seconds
        self._options: dict = {"temperature": temperature}
        if seed is not None:
            self._options["seed"] = seed

    async def complete(
        self,
        messages: list[Message],
        tools: list[ToolDefinition] | None = None,
        json_mode: bool = False,
    ) -> CompletionResult:
        payload = self._build_chat_payload(messages, tools, stream=False)
        if json_mode and not tools:
            payload["format"] = "json"
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            response = await client.post(f"{self._base_url}/api/chat", json=payload)
            response.raise_for_status()
            return self._parse_completion(response.json())

    async def stream(
        self,
        messages: list[Message],
        tools: list[ToolDefinition] | None = None,
    ) -> AsyncIterator[StreamEvent]:
        payload = self._build_chat_payload(messages, tools, stream=True)
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            async with client.stream(
                "POST", f"{self._base_url}/api/chat", json=payload
            ) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if not line.strip():
                        continue
                    chunk = json.loads(line)
                    message = chunk.get("message", {})

                    content = message.get("content", "")
                    if content:
                        yield StreamEvent(kind="token", text=content)

                    for raw_call in message.get("tool_calls", []) or []:
                        yield StreamEvent(
                            kind="tool_call",
                            tool_call=_parse_tool_call(raw_call),
                        )

                    if chunk.get("done"):
                        break
        yield StreamEvent(kind="done")

    async def embed(self, texts: list[str]) -> list[list[float]]:
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            response = await client.post(
                f"{self._base_url}/api/embed",
                json={"model": self._embed_model, "input": texts},
            )
            response.raise_for_status()
            return response.json()["embeddings"]

    def _build_chat_payload(
        self,
        messages: list[Message],
        tools: list[ToolDefinition] | None,
        stream: bool,
    ) -> dict:
        payload: dict = {
            "model": self._chat_model,
            "messages": [_message_to_dict(m) for m in messages],
            "stream": stream,
            # Deterministic by default: retrieval-grounded answers and the
            # evaluation must not change from run to run.
            "options": self._options,
        }
        if tools:
            payload["tools"] = [_tool_to_dict(t) for t in tools]
        return payload

    @staticmethod
    def _parse_completion(data: dict) -> CompletionResult:
        message = data.get("message", {})
        tool_calls = [_parse_tool_call(tc) for tc in message.get("tool_calls", []) or []]
        return CompletionResult(
            content=message.get("content", ""),
            tool_calls=tool_calls,
            input_tokens=data.get("prompt_eval_count", 0),
            output_tokens=data.get("eval_count", 0),
            model=data.get("model", ""),
        )


def _message_to_dict(message: Message) -> dict:
    result: dict = {"role": message.role, "content": message.content}
    if message.tool_call_id:
        result["tool_call_id"] = message.tool_call_id
    if message.name:
        result["name"] = message.name
    if message.tool_calls:
        result["tool_calls"] = [
            {"function": {"name": call.name, "arguments": call.arguments}}
            for call in message.tool_calls
        ]
    return result


def _tool_to_dict(tool: ToolDefinition) -> dict:
    return {
        "type": "function",
        "function": {
            "name": tool.name,
            "description": tool.description,
            "parameters": tool.parameters,
        },
    }


def _parse_tool_call(raw: dict) -> ToolCall:
    function = raw.get("function", {})
    return ToolCall(
        id=raw.get("id", ""),
        name=function.get("name", ""),
        arguments=function.get("arguments", {}),
    )
