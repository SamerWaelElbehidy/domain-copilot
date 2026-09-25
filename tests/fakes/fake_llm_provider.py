from __future__ import annotations

import re
import zlib
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
        self.stream_closed_early = False
        self.streams_finished = 0

    async def complete(
        self,
        messages: list[Message],
        tools: list[ToolDefinition] | None = None,
        json_mode: bool = False,
    ) -> CompletionResult:
        self.received_messages.append(messages)
        if self._responses:
            return self._responses.pop(0)
        return CompletionResult(content="", model="fake")

    async def stream(
        self,
        messages: list[Message],
        tools: list[ToolDefinition] | None = None,
        json_mode: bool = False,
    ) -> AsyncIterator[StreamEvent]:
        result = await self.complete(messages, tools, json_mode)
        self.stream_closed_early = True
        try:
            for word in result.content.split():
                yield StreamEvent(kind="token", text=word + " ")
            self.stream_closed_early = False
            yield StreamEvent(
                kind="done",
                input_tokens=result.input_tokens,
                output_tokens=result.output_tokens,
                model=result.model,
            )
        finally:
            self.streams_finished += 1

    async def embed(self, texts: list[str]) -> list[list[float]]:
        """Hashed bag-of-words: deterministic, and texts sharing words get
        similar vectors, so retrieval order in tests is meaningful."""
        vectors = []
        for text in texts:
            vector = [0.0] * self._embedding_dim
            for token in re.findall(r"[a-z0-9]+", text.lower()):
                vector[zlib.crc32(token.encode()) % self._embedding_dim] += 1.0
            vectors.append(vector)
        return vectors
