from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any

from domain.entities.run import Run
from domain.errors.domain_errors import TamperedRunError


@dataclass(frozen=True)
class ReplayFrame:
    step_index: int
    name: str
    agent_name: str | None
    provider_used: str | None
    status: str
    input_snapshot: dict[str, Any]
    output_snapshot: dict[str, Any]
    input_tokens: int
    output_tokens: int


def replay_run(run: Run) -> Iterator[ReplayFrame]:
    """T4 replay (ADR-0006): plays back exactly what was recorded, in order.
    It never calls an LLM, vector store or tool, so replaying twice gives
    identical output by construction. The hash chain is verified first; a
    run whose log was edited after the fact is refused, not replayed."""
    if not run.verify_chain():
        raise TamperedRunError(f"run {run.run_id}: audit log failed hash-chain verification")
    for step in run.steps:
        yield ReplayFrame(
            step_index=step.step_index,
            name=step.name,
            agent_name=step.agent_name,
            provider_used=step.provider_used,
            status=step.status,
            input_snapshot=step.input_snapshot,
            output_snapshot=step.output_snapshot,
            input_tokens=step.input_tokens,
            output_tokens=step.output_tokens,
        )
