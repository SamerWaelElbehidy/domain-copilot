from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any

GENESIS_HASH = "0" * 64


def compute_step_hash(
    *,
    step_index: int,
    name: str,
    output_snapshot: dict[str, Any],
    previous_hash: str,
) -> str:
    """Chains each step to the one before it (git-commit style), per
    ADR-0006: a persisted step edited after the fact will no longer match
    its recomputed hash."""
    payload = json.dumps(
        {
            "step_index": step_index,
            "name": name,
            "output": output_snapshot,
            "prev": previous_hash,
        },
        sort_keys=True,
        default=str,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class RunStep:
    """One recorded unit of orchestration work. `input_snapshot` /
    `output_snapshot` are what `replay <run-id>` plays back -- never
    regenerated live (ADR-0006)."""

    step_index: int
    name: str
    agent_name: str | None
    provider_used: str | None
    input_snapshot: dict[str, Any]
    output_snapshot: dict[str, Any]
    input_tokens: int
    output_tokens: int
    started_at: datetime
    finished_at: datetime
    status: str  # "success" | "failed" | "retried"
    step_hash: str

    @staticmethod
    def create(
        *,
        step_index: int,
        name: str,
        agent_name: str | None,
        provider_used: str | None,
        input_snapshot: dict[str, Any],
        output_snapshot: dict[str, Any],
        input_tokens: int,
        output_tokens: int,
        started_at: datetime,
        finished_at: datetime,
        status: str,
        previous_hash: str,
    ) -> "RunStep":
        step_hash = compute_step_hash(
            step_index=step_index,
            name=name,
            output_snapshot=output_snapshot,
            previous_hash=previous_hash,
        )
        return RunStep(
            step_index=step_index,
            name=name,
            agent_name=agent_name,
            provider_used=provider_used,
            input_snapshot=input_snapshot,
            output_snapshot=output_snapshot,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            started_at=started_at,
            finished_at=finished_at,
            status=status,
            step_hash=step_hash,
        )
