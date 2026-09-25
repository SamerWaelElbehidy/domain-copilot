from __future__ import annotations

import asyncio
import dataclasses
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from application.agents.diagnostic_planner import DiagnosticSafetyPlanner
from application.agents.names import ORCHESTRATOR
from application.agents.symptom_matcher import SymptomMatcher
from application.agents.tool_loop import LoopResult
from application.agents.tool_registry import ToolRegistry
from application.agents.work_order_generator import WorkOrderGenerator
from application.ports.run_repository import RunRepository
from application.ports.work_order_repository import WorkOrderRepository
from domain.entities.run import Run
from domain.entities.work_order import WorkOrder
from domain.errors.domain_errors import (
    AgentOutputError,
    InvalidReviewEditError,
    InvalidRunTransitionError,
    LowEvidenceError,
    MissingSafetyPrerequisiteError,
    StepFailedError,
)
from domain.value_objects.run_state import ALLOWED_TRANSITIONS, RunState
from domain.value_objects.run_step import RunStep

Emit = Callable[[dict[str, Any]], Awaitable[None]]
Fallback = Callable[[str], Awaitable[dict[str, Any]]]

# Failures worth retrying: malformed model output, timeouts, transport errors.
# Refusals (low evidence, missing safety) are answers, not failures, and are
# never retried.
RETRYABLE = (AgentOutputError, TimeoutError, ConnectionError, OSError)


@dataclass(frozen=True)
class StepPolicy:
    """FR-5 controls applied to every step."""

    timeout_seconds: float = 60.0
    max_attempts: int = 3
    backoff_base_seconds: float = 0.5


@dataclass
class StepOutcome:
    value: Any
    output: dict[str, Any]
    input_tokens: int = 0
    output_tokens: int = 0
    provider: str | None = None


def jsonable(value: Any) -> Any:
    """Snapshots are persisted as JSON and replayed, so they must contain
    plain data only."""
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return jsonable(dataclasses.asdict(value))
    if isinstance(value, dict):
        return {str(k): jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [jsonable(v) for v in value]
    if isinstance(value, datetime):
        return value.isoformat()
    if hasattr(value, "value") and not isinstance(value, (str, int, float, bool)):
        return value.value
    return value


def loop_snapshot(loop: LoopResult) -> dict[str, Any]:
    return {
        "tool_trace": [
            {"tool": t.tool_name, "arguments": jsonable(t.arguments), "result": jsonable(t.result)}
            for t in loop.trace
        ],
        "raw_model_output": loop.content,
    }


class CopilotOrchestrator:
    """State-machine orchestrator (ADR-0005) for the D5 workflow.

    Every step goes through one wrapper that applies the per-step timeout,
    retry with exponential backoff, and records a hash-chained RunStep for
    each attempt (ADR-0006), so a run is inspectable and replayable from its
    id. Refusals end the run in REFUSED_LOW_EVIDENCE; exhausted retries
    degrade to plain RAG when a fallback exists, otherwise FAILED. Only
    `decide()` can approve, and only after that does the orchestrator hold
    an ApprovalToken that lets it call the gated dispatch tool."""

    def __init__(
        self,
        *,
        matcher: SymptomMatcher,
        planner: DiagnosticSafetyPlanner,
        generator: WorkOrderGenerator,
        registry: ToolRegistry,
        run_repository: RunRepository,
        work_order_repository: WorkOrderRepository,
        policy: StepPolicy | None = None,
        fallback: Fallback | None = None,
        prompt_versions: dict[str, str] | None = None,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        id_factory: Callable[[], str] = lambda: f"run-{uuid.uuid4().hex[:12]}",
        emit: Emit | None = None,
    ) -> None:
        self._matcher = matcher
        self._planner = planner
        self._generator = generator
        self._registry = registry
        self._runs = run_repository
        self._work_orders = work_order_repository
        self._policy = policy or StepPolicy()
        self._fallback = fallback
        self._prompts = prompt_versions or {}
        self._clock = clock
        self._sleep = sleep
        self._id_factory = id_factory
        self._emit = emit

    # ---- public API ---------------------------------------------------------

    async def begin(self, created_by: str | None = None) -> Run:
        """Creates and persists the run so callers (the API) can hand back a
        run id before the slow pipeline has finished."""
        run = Run(
            run_id=self._id_factory(), equipment_id=None, started_at=self._clock(),
            created_by=created_by,
        )
        await self._runs.save(run)
        return run

    async def start(self, symptom: str, created_by: str | None = None) -> Run:
        return await self.execute(await self.begin(created_by), symptom)

    async def execute(self, run: Run, symptom: str) -> Run:
        try:
            await self._pipeline(run, symptom)
        except asyncio.CancelledError:
            await self._close_failed(run, "cancelled by client")
            raise
        return run

    async def decide(
        self,
        run_id: str,
        *,
        reviewer: str,
        decision: str,
        comment: str = "",
        edits: dict[str, Any] | None = None,
    ) -> Run:
        run = await self._runs.get(run_id)
        if run is None:
            raise InvalidRunTransitionError(f"unknown run '{run_id}'")
        if run.state != RunState.PENDING_APPROVAL:
            raise InvalidRunTransitionError(
                f"run {run_id} is {run.state.value}, not awaiting approval"
            )
        if decision not in {"approve", "reject", "edit_and_approve"}:
            raise ValueError(f"unknown decision '{decision}'")

        work_order = await self._work_order_for(run)
        now = self._clock()

        if decision == "reject":
            work_order.reject(reviewer, now)
            await self._work_orders.save(work_order)
            self._record(run, "human_decision", None, None,
                         {"reviewer": reviewer, "decision": decision, "comment": comment},
                         {"work_order_status": work_order.status.value}, 0, 0, now, now)
            run.transition_to(RunState.REJECTED)
            await self._runs.save(run)
            await self._publish(run, "rejected")
            return run

        if decision == "edit_and_approve":
            self._apply_edits(work_order, edits or {})
            self._record(run, "reviewer_edit", None, None,
                         {"reviewer": reviewer, "edits": jsonable(edits or {})},
                         {"diagnostic_steps": list(work_order.diagnostic_steps),
                          "safety_checklist": list(work_order.safety_checklist),
                          "symptom_description": work_order.symptom_description},
                         0, 0, now, now)

        work_order.approve(reviewer, now)
        await self._work_orders.save(work_order)
        self._record(run, "human_decision", None, None,
                     {"reviewer": reviewer, "decision": decision, "comment": comment},
                     {"work_order_status": work_order.status.value}, 0, 0, now, now)
        run.transition_to(RunState.APPROVED)
        await self._runs.save(run)

        token = self._registry.approval_authority.issue(work_order.work_order_id, reviewer, now)
        started = self._clock()
        outcome = await self._registry.execute(
            ORCHESTRATOR, "dispatch_work_order",
            {"work_order_id": work_order.work_order_id}, approval=token,
        )
        self._record(run, "dispatch", None, None,
                     {"work_order_id": work_order.work_order_id, "approved_by": reviewer},
                     jsonable(outcome), 0, 0, started, self._clock())
        run.transition_to(RunState.DISPATCHED)
        await self._runs.save(run)
        await self._publish(run, "dispatched")
        return run

    # ---- pipeline -----------------------------------------------------------

    async def _pipeline(self, run: Run, symptom: str) -> None:
        self._record(run, "receive", None, None, {"symptom": symptom}, {"accepted": True},
                     0, 0, self._clock(), self._clock())

        run.transition_to(RunState.MATCHING_SYMPTOM)
        match = await self._guarded(
            run, "match_symptom", self._matcher.name, {"symptom": symptom},
            self._match(symptom), symptom,
        )
        if match is None:
            return
        run.equipment_id = match.equipment_id

        run.transition_to(RunState.DIAGNOSING)
        plan = await self._guarded(
            run, "diagnose", self._planner.name,
            {"symptom": symptom, "equipment_id": match.equipment_id},
            self._diagnose(symptom, match), symptom,
        )
        if plan is None:
            return

        run.transition_to(RunState.DRAFTING_WORK_ORDER)
        draft = await self._guarded(
            run, "draft_work_order", self._generator.name,
            {"symptom": symptom, "equipment_id": match.equipment_id},
            self._draft(symptom, match, plan), symptom,
        )
        if draft is None:
            return

        run.transition_to(RunState.PENDING_APPROVAL)
        self._record(run, "await_approval", None, None, {"work_order_id": draft.work_order_id},
                     {"status": "pending_approval"}, 0, 0, self._clock(), self._clock())
        await self._runs.save(run)
        await self._publish(run, "awaiting_approval")

    def _match(self, symptom: str) -> Callable[[], Awaitable[StepOutcome]]:
        async def action() -> StepOutcome:
            result, loop = await self._matcher.run(symptom)
            return StepOutcome(result, {"result": jsonable(result), **loop_snapshot(loop)},
                               loop.input_tokens, loop.output_tokens, loop.model)
        return action

    def _diagnose(self, symptom: str, match: Any) -> Callable[[], Awaitable[StepOutcome]]:
        async def action() -> StepOutcome:
            plan, loop = await self._planner.run(symptom, match)
            return StepOutcome(plan, {"result": jsonable(plan), **loop_snapshot(loop)},
                               loop.input_tokens, loop.output_tokens, loop.model)
        return action

    def _draft(self, symptom: str, match: Any, plan: Any) -> Callable[[], Awaitable[StepOutcome]]:
        async def action() -> StepOutcome:
            draft, loop = await self._generator.run(symptom, match, plan)
            return StepOutcome(draft, {"result": jsonable(draft), **loop_snapshot(loop)},
                               loop.input_tokens, loop.output_tokens, loop.model)
        return action

    # ---- the FR-5 step wrapper ----------------------------------------------

    async def _guarded(
        self,
        run: Run,
        name: str,
        agent: str,
        input_snapshot: dict[str, Any],
        action: Callable[[], Awaitable[StepOutcome]],
        symptom: str,
    ) -> Any | None:
        """Returns the step's value, or None if the run ended (refused,
        degraded, or failed) -- the caller stops when it gets None."""
        input_snapshot = {**input_snapshot, "prompt": self._prompts.get(agent)}
        await self._publish(run, "step_started", step=name, agent=agent)
        last_error: Exception | None = None

        for attempt in range(1, self._policy.max_attempts + 1):
            started = self._clock()
            try:
                outcome = await asyncio.wait_for(action(), self._policy.timeout_seconds)
            except (LowEvidenceError, MissingSafetyPrerequisiteError) as refusal:
                self._record(run, name, agent, None, input_snapshot,
                             {"refused": type(refusal).__name__, "reason": str(refusal)},
                             0, 0, started, self._clock(), status="refused")
                run.transition_to(RunState.REFUSED_LOW_EVIDENCE)
                await self._runs.save(run)
                await self._publish(run, "refused", reason=str(refusal))
                return None
            except RETRYABLE as exc:
                last_error = exc
                final = attempt == self._policy.max_attempts
                self._record(run, name, agent, None, input_snapshot,
                             {"error": type(exc).__name__, "message": str(exc), "attempt": attempt},
                             0, 0, started, self._clock(),
                             status="failed" if final else "retried")
                await self._runs.save(run)
                if not final:
                    await self._sleep(self._policy.backoff_base_seconds * 2 ** (attempt - 1))
                continue
            except Exception as exc:
                self._record(run, name, agent, None, input_snapshot,
                             {"error": type(exc).__name__, "message": str(exc)},
                             0, 0, started, self._clock(), status="failed")
                await self._close_failed(run, f"{name}: {type(exc).__name__}")
                raise

            self._record(run, name, agent, outcome.provider, input_snapshot, outcome.output,
                         outcome.input_tokens, outcome.output_tokens, started, self._clock())
            await self._runs.save(run)
            await self._publish(run, "step_finished", step=name, agent=agent)
            return outcome.value

        await self._degrade_or_fail(run, name, symptom, last_error)
        return None

    async def _degrade_or_fail(
        self, run: Run, step: str, symptom: str, error: Exception | None
    ) -> None:
        can_degrade = (
            self._fallback is not None
            and RunState.DEGRADED_PLAIN_RAG in _allowed(run.state)
        )
        if can_degrade:
            started = self._clock()
            answer = await self._fallback(symptom)  # type: ignore[misc]
            self._record(run, "degrade_to_plain_rag", None, None,
                         {"failed_step": step, "error": str(error)}, jsonable(answer),
                         0, 0, started, self._clock())
            run.transition_to(RunState.DEGRADED_PLAIN_RAG)
            await self._runs.save(run)
            await self._publish(run, "degraded", failed_step=step)
            return
        await self._close_failed(run, f"{step} failed after retries: {error}")
        raise StepFailedError(f"step '{step}' failed after {self._policy.max_attempts} attempts")

    # ---- helpers ---------------------------------------------------------------

    async def work_order_of(self, run: Run) -> WorkOrder | None:
        try:
            return await self._work_order_for(run)
        except InvalidRunTransitionError:
            return None

    async def _work_order_for(self, run: Run) -> WorkOrder:
        for step in reversed(run.steps):
            work_order_id = (step.output_snapshot.get("result") or {}).get("work_order_id")
            if work_order_id:
                work_order = await self._work_orders.get(work_order_id)
                if work_order is not None:
                    return work_order
        raise InvalidRunTransitionError(f"run {run.run_id} has no work order to decide on")

    @staticmethod
    def _apply_edits(work_order: WorkOrder, edits: dict[str, Any]) -> None:
        allowed = {"diagnostic_steps", "safety_checklist", "symptom_description"}
        unknown = set(edits) - allowed
        if unknown:
            raise InvalidReviewEditError(f"fields not editable by a reviewer: {sorted(unknown)}")
        if "safety_checklist" in edits:
            missing = set(work_order.safety_checklist) - set(edits["safety_checklist"])
            if missing:
                raise InvalidReviewEditError(
                    "a reviewer may add safety steps but never remove them "
                    f"({len(missing)} would be dropped)"
                )
            work_order.safety_checklist = list(edits["safety_checklist"])
        if "diagnostic_steps" in edits:
            work_order.diagnostic_steps = list(edits["diagnostic_steps"])
        if "symptom_description" in edits:
            work_order.symptom_description = str(edits["symptom_description"])

    async def _close_failed(self, run: Run, reason: str) -> None:
        if RunState.FAILED in _allowed(run.state):
            now = self._clock()
            self._record(run, "run_failed", None, None, {}, {"reason": reason}, 0, 0, now, now,
                         status="failed")
            run.transition_to(RunState.FAILED)
        await self._runs.save(run)
        await self._publish(run, "failed", reason=reason)

    def _record(
        self,
        run: Run,
        name: str,
        agent: str | None,
        provider: str | None,
        input_snapshot: dict[str, Any],
        output_snapshot: dict[str, Any],
        input_tokens: int,
        output_tokens: int,
        started_at: datetime,
        finished_at: datetime,
        status: str = "success",
    ) -> None:
        run.record_step(
            RunStep.create(
                step_index=len(run.steps),
                name=name,
                agent_name=agent,
                provider_used=provider,
                input_snapshot=jsonable(input_snapshot),
                output_snapshot=jsonable(output_snapshot),
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                started_at=started_at,
                finished_at=finished_at,
                status=status,
                previous_hash=run.last_step_hash,
            )
        )

    async def _publish(self, run: Run, kind: str, **data: Any) -> None:
        if self._emit is not None:
            event = {"run_id": run.run_id, "state": run.state.value, "event": kind, **data}
            await self._emit(event)


def _allowed(state: RunState) -> frozenset[RunState]:
    return ALLOWED_TRANSITIONS[state]
