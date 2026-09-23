from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from domain.errors.domain_errors import InvalidRunTransitionError, TamperedRunError
from domain.value_objects.run_state import ALLOWED_TRANSITIONS, RunState
from domain.value_objects.run_step import GENESIS_HASH, RunStep, compute_step_hash


@dataclass
class Run:
    """The orchestration state machine for one D5 workflow execution
    (ADR-0005), and the audit/replay record for T4 (ADR-0006)."""

    run_id: str
    equipment_id: str | None
    started_at: datetime
    state: RunState = RunState.RECEIVED
    steps: list[RunStep] = field(default_factory=list)

    def transition_to(self, new_state: RunState) -> None:
        allowed = ALLOWED_TRANSITIONS[self.state]
        if new_state not in allowed:
            raise InvalidRunTransitionError(
                f"Run {self.run_id}: cannot go from {self.state.value} to "
                f"{new_state.value} (allowed: {sorted(s.value for s in allowed)})."
            )
        self.state = new_state

    def record_step(self, step: RunStep) -> None:
        if step.step_index != len(self.steps):
            raise InvalidRunTransitionError(
                f"Run {self.run_id}: out-of-order step "
                f"(expected index {len(self.steps)}, got {step.step_index})."
            )
        expected_hash = compute_step_hash(
            step_index=step.step_index,
            name=step.name,
            output_snapshot=step.output_snapshot,
            previous_hash=self.last_step_hash,
        )
        if step.step_hash != expected_hash:
            raise TamperedRunError(
                f"Run {self.run_id}: step {step.step_index} hash does not "
                "chain from the previous step -- build it via RunStep.create()."
            )
        self.steps.append(step)

    def verify_chain(self) -> bool:
        """Recomputes every step's hash from scratch; False means a
        persisted step was edited after the fact (ADR-0006)."""
        previous_hash = GENESIS_HASH
        for step in self.steps:
            expected = compute_step_hash(
                step_index=step.step_index,
                name=step.name,
                output_snapshot=step.output_snapshot,
                previous_hash=previous_hash,
            )
            if step.step_hash != expected:
                return False
            previous_hash = step.step_hash
        return True

    @property
    def last_step_hash(self) -> str:
        """The hash the next RunStep.create() call must chain from."""
        return self.steps[-1].step_hash if self.steps else GENESIS_HASH

    @property
    def is_terminal(self) -> bool:
        return len(ALLOWED_TRANSITIONS[self.state]) == 0
