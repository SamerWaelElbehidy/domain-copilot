from __future__ import annotations

from collections.abc import AsyncIterator

from application.ports.llm_provider import (
    CompletionResult,
    LLMProvider,
    Message,
    StreamEvent,
    ToolDefinition,
)


class FakeLLMProvider(LLMProvider):
    """Deterministic stand-in for tests -- no network calls. Configure
    `responses` with the CompletionResult(s) to return, in order."""

    def __init__(
        self,
        responses: list[CompletionResult] | None = None,
        embedding_dim: int = 8,
    ) -> None:
        self._responses = list(responses or [])
        self._embedding_dim = embedding_dim
        self.received_messages: list[list[Message]] = []

    async def complete(
        self,
        messages: list[Message],
        tools: list[ToolDefinition] | None = None,
    ) -> CompletionResult:
        self.received_messages.append(messages)
        if self._responses:
            return self._responses.pop(0)
        return CompletionResult(content="", model="fake")

    async def stream(
        self,
        messages: list[Message],
        tools: list[ToolDefinition] | None = None,
    ) -> AsyncIterator[StreamEvent]:
        result = await self.complete(messages, tools)
        for word in result.content.split():
            yield StreamEvent(kind="token", text=word + " ")
        yield StreamEvent(kind="done")

    async def embed(self, texts: list[str]) -> list[list[float]]:
        return [[float(len(t) % 7)] * self._embedding_dim for t in texts]
