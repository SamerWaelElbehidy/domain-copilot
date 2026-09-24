from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class ToolCall:
    id: str
    name: str
    arguments: dict[str, Any]


@dataclass(frozen=True)
class Message:
    role: str  # "system" | "user" | "assistant" | "tool"
    content: str
    tool_call_id: str | None = None
    name: str | None = None
    tool_calls: tuple[ToolCall, ...] = ()


@dataclass(frozen=True)
class ToolDefinition:
    name: str
    description: str
    parameters: dict[str, Any]  # JSON schema, validated before execution (LLM Top 10)


@dataclass(frozen=True)
class CompletionResult:
    content: str
    tool_calls: list[ToolCall] = field(default_factory=list)
    input_tokens: int = 0
    output_tokens: int = 0
    model: str = ""


@dataclass(frozen=True)
class StreamEvent:
    kind: str  # "token" | "tool_call" | "done"
    text: str = ""
    tool_call: ToolCall | None = None


class LLMProvider(ABC):
    """Single port covering completion, streaming, tool calling and
    embeddings (ADR-0003). Every concrete adapter -- hosted API or local
    model -- implements all four methods, so the fallback chain can swap
    providers with configuration only, never a call-site change."""

    @abstractmethod
    async def complete(
        self,
        messages: list[Message],
        tools: list[ToolDefinition] | None = None,
        json_mode: bool = False,
    ) -> CompletionResult:
        """json_mode asks the provider to constrain output to valid JSON.
        Callers still validate the result; this only makes small models
        far less likely to answer in prose."""
        ...

    @abstractmethod
    def stream(
        self,
        messages: list[Message],
        tools: list[ToolDefinition] | None = None,
    ) -> AsyncIterator[StreamEvent]: ...

    @abstractmethod
    async def embed(self, texts: list[str]) -> list[list[float]]: ...
