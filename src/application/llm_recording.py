from __future__ import annotations

import asyncio
import time
from collections.abc import AsyncIterator, Callable, Mapping
from datetime import UTC, datetime

from application.correlation import get_correlation_id, get_usage_context
from application.ports.llm_call_repository import LLMCall, LLMCallRepository
from application.ports.llm_provider import (
    CompletionResult,
    LLMProvider,
    Message,
    StreamEvent,
    ToolDefinition,
)

# (USD per 1,000 input tokens, USD per 1,000 output tokens). Local models are
# free. Hosted prices change, so treat these as configuration, not fact.
DEFAULT_PRICES: Mapping[str, tuple[float, float]] = {}


def estimate_cost(
    prices: Mapping[str, tuple[float, float]], model: str, input_tokens: int, output_tokens: int
) -> float:
    per_in, per_out = prices.get(model, (0.0, 0.0))
    return round(input_tokens / 1000 * per_in + output_tokens / 1000 * per_out, 6)


class RecordingLLMProvider(LLMProvider):
    """Decorator that persists every model call with tokens, cost, latency,
    the correlation id and the caller's usage context. It sits at the
    composition root, so no agent or use case knows accounting exists."""

    def __init__(
        self,
        inner: LLMProvider,
        repository: LLMCallRepository,
        provider_name: str,
        prices: Mapping[str, tuple[float, float]] = DEFAULT_PRICES,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._inner = inner
        self._repository = repository
        self._provider_name = provider_name
        self._prices = prices
        self._clock = clock

    async def _record(
        self,
        operation: str,
        model: str,
        tin: int,
        tout: int,
        started: float,
        status: str,
        provider: str = "",
    ) -> None:
        context = get_usage_context()
        await self._repository.record(
            LLMCall(
                correlation_id=get_correlation_id(),
                user_id=context.user_id,
                run_id=context.run_id,
                purpose=context.purpose,
                provider=provider or self._provider_name,
                model=model,
                operation=operation,
                input_tokens=tin,
                output_tokens=tout,
                cost_usd=estimate_cost(self._prices, model, tin, tout),
                latency_ms=int((time.perf_counter() - started) * 1000),
                status=status,
                created_at=self._clock(),
            )
        )

    async def complete(
        self,
        messages: list[Message],
        tools: list[ToolDefinition] | None = None,
        json_mode: bool = False,
    ) -> CompletionResult:
        started = time.perf_counter()
        try:
            result = await self._inner.complete(messages, tools, json_mode)
        except Exception:
            await self._record("complete", "", 0, 0, started, "error")
            raise
        await self._record(
            "complete", result.model, result.input_tokens, result.output_tokens, started, "ok",
            result.provider,
        )
        return result

    async def stream(
        self,
        messages: list[Message],
        tools: list[ToolDefinition] | None = None,
        json_mode: bool = False,
    ) -> AsyncIterator[StreamEvent]:
        started = time.perf_counter()
        inner = self._inner.stream(messages, tools, json_mode)
        status, model, tin, tout, served_by = "cancelled", "", 0, 0, ""
        try:
            async for event in inner:
                if event.kind == "done":
                    status, model, served_by = "ok", event.model, event.provider
                    tin, tout = event.input_tokens, event.output_tokens
                yield event
        except asyncio.CancelledError:
            raise
        except Exception:
            status = "error"
            raise
        finally:
            # Closing the inner iterator is what stops generation upstream when
            # the client goes away (FR-6).
            await inner.aclose()
            await asyncio.shield(
                self._record("stream", model, tin, tout, started, status, served_by)
            )

    async def embed(self, texts: list[str]) -> list[list[float]]:
        started = time.perf_counter()
        try:
            vectors = await self._inner.embed(texts)
        except Exception:
            await self._record("embed", "", 0, 0, started, "error")
            raise
        await self._record("embed", "embedding", sum(len(t) for t in texts) // 4, 0, started, "ok")
        return vectors
