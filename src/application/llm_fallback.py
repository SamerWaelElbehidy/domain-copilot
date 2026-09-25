from __future__ import annotations

import dataclasses
import logging
import time
from collections.abc import AsyncIterator, Callable, Sequence

from application.ports.llm_provider import (
    CompletionResult,
    LLMProvider,
    Message,
    ProviderUnavailableError,
    StreamEvent,
    ToolDefinition,
)

log = logging.getLogger("llm.fallback")


class FallbackLLMProvider(LLMProvider):
    """Tries providers in order and fails over when one is unavailable (FR-4,
    ADR-0007). Callers see one LLMProvider and never learn there are several.

    - A provider that fails `failure_threshold` times in a row is skipped for
      `cooldown_seconds` (a small circuit breaker), so a dead host costs one
      timeout, not one timeout per request. If every provider is tripped,
      all are tried anyway rather than refusing to try.
    - Streaming fails over only before the first event. Once tokens have
      reached the caller they cannot be un-sent, so a mid-stream failure is
      raised, not silently spliced onto another model's output.
    - Embeddings never fail over. Vectors from different models live in
      different spaces, so mixing them would corrupt retrieval without any
      error. The embedding provider is fixed, and its outage is an outage."""

    def __init__(
        self,
        providers: Sequence[tuple[str, LLMProvider]],
        embedding_provider: str | None = None,
        failure_threshold: int = 3,
        cooldown_seconds: float = 30.0,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if not providers:
            raise ValueError("at least one provider is required")
        self._providers = list(providers)
        names = [name for name, _ in self._providers]
        if len(set(names)) != len(names):
            raise ValueError("provider names must be unique")
        self._embedder = embedding_provider or names[0]
        if self._embedder not in names:
            raise ValueError(f"embedding provider '{self._embedder}' is not in the chain")
        self._threshold = failure_threshold
        self._cooldown = cooldown_seconds
        self._clock = clock
        self._failures = {name: 0 for name in names}
        self._open_until = {name: 0.0 for name in names}

    # ---- circuit breaker ------------------------------------------------------

    def _candidates(self) -> list[tuple[str, LLMProvider]]:
        now = self._clock()
        closed = [(n, p) for n, p in self._providers if self._open_until[n] <= now]
        return closed or list(self._providers)

    def _succeeded(self, name: str) -> None:
        self._failures[name] = 0
        self._open_until[name] = 0.0

    def _failed(self, name: str, error: Exception) -> None:
        self._failures[name] += 1
        log.warning("provider %s unavailable (%s)", name, error)
        if self._failures[name] >= self._threshold:
            self._open_until[name] = self._clock() + self._cooldown
            self._failures[name] = 0
            log.warning("provider %s skipped for %.0fs", name, self._cooldown)

    def status(self) -> dict[str, str]:
        now = self._clock()
        return {n: ("open" if self._open_until[n] > now else "closed") for n, _ in self._providers}

    # ---- LLMProvider ----------------------------------------------------------

    async def complete(
        self,
        messages: list[Message],
        tools: list[ToolDefinition] | None = None,
        json_mode: bool = False,
    ) -> CompletionResult:
        errors: list[str] = []
        for name, provider in self._candidates():
            try:
                result = await provider.complete(messages, tools, json_mode)
            except ProviderUnavailableError as exc:
                self._failed(name, exc)
                errors.append(str(exc))
                continue
            self._succeeded(name)
            return dataclasses.replace(result, provider=name)
        raise ProviderUnavailableError("all providers failed: " + "; ".join(errors))

    async def stream(
        self,
        messages: list[Message],
        tools: list[ToolDefinition] | None = None,
        json_mode: bool = False,
    ) -> AsyncIterator[StreamEvent]:
        errors: list[str] = []
        for name, provider in self._candidates():
            inner = provider.stream(messages, tools, json_mode)
            started = False
            try:
                async for event in inner:
                    started = True
                    yield dataclasses.replace(event, provider=name)
            except ProviderUnavailableError as exc:
                self._failed(name, exc)
                if started:
                    raise
                errors.append(str(exc))
                continue
            finally:
                await inner.aclose()
            self._succeeded(name)
            return
        raise ProviderUnavailableError("all providers failed: " + "; ".join(errors))

    async def embed(self, texts: list[str]) -> list[list[float]]:
        provider = dict(self._providers)[self._embedder]
        try:
            vectors = await provider.embed(texts)
        except ProviderUnavailableError as exc:
            self._failed(self._embedder, exc)
            raise
        self._succeeded(self._embedder)
        return vectors
