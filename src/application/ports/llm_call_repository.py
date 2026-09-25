from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class LLMCall:
    """One model call, persisted for per-request token and cost accounting
    (FR-9). correlation_id links it to the HTTP request, and run_id (when
    there is one) to the orchestrator run and its steps."""

    correlation_id: str
    user_id: str | None
    run_id: str | None
    purpose: str
    provider: str
    model: str
    operation: str  # "complete" | "stream" | "embed"
    input_tokens: int
    output_tokens: int
    cost_usd: float
    latency_ms: int
    status: str  # "ok" | "error" | "cancelled"
    created_at: datetime


@dataclass(frozen=True)
class UsageRow:
    user_id: str | None
    calls: int
    input_tokens: int
    output_tokens: int
    cost_usd: float


class LLMCallRepository(ABC):
    @abstractmethod
    async def record(self, call: LLMCall) -> None: ...

    @abstractmethod
    async def usage_by_user(self, since: datetime) -> list[UsageRow]: ...

    @abstractmethod
    async def calls_for_correlation(self, correlation_id: str) -> list[LLMCall]: ...

    @abstractmethod
    async def calls_for_run(self, run_id: str) -> list[LLMCall]: ...
