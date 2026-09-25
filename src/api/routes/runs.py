from __future__ import annotations

import json
import re
from collections.abc import AsyncIterator
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from api.container import Container
from api.deps import current_user, get_container, require
from application.use_cases.replay_run import replay_run
from domain.entities.run import Run
from domain.entities.user import User
from domain.entities.work_order import WorkOrder
from domain.errors.domain_errors import PermissionDeniedError
from domain.value_objects.role import Permission, has_permission
from domain.value_objects.run_state import RunState

router = APIRouter(tags=["runs"])
_can_start = require(Permission.START_RUN)
_can_decide = require(Permission.DECIDE_WORK_ORDER)
_can_replay = require(Permission.REPLAY_RUN)
_CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


class StartRunRequest(BaseModel):
    symptom: str = Field(min_length=5, max_length=1000)


class DecisionRequest(BaseModel):
    decision: Literal["approve", "reject", "edit_and_approve"]
    comment: str = Field(default="", max_length=1000)
    edits: dict[str, Any] | None = None


def _work_order_json(wo: WorkOrder | None) -> dict[str, Any] | None:
    if wo is None:
        return None
    return {
        "work_order_id": wo.work_order_id,
        "equipment_id": wo.equipment_id,
        "symptom_description": wo.symptom_description,
        "diagnostic_steps": wo.diagnostic_steps,
        "safety_checklist": wo.safety_checklist,
        "citations": [c.__dict__ for c in wo.citations],
        "status": wo.status.value,
        "approved_by": wo.approved_by,
    }


def _summary(run: Run) -> dict[str, Any]:
    return {
        "run_id": run.run_id,
        "state": run.state.value,
        "equipment_id": run.equipment_id,
        "started_at": run.started_at.isoformat(),
        "created_by": run.created_by,
    }


def _can_see(user: User, run: Run) -> bool:
    if has_permission(user.role, Permission.VIEW_ALL_RUNS):
        return True
    return has_permission(user.role, Permission.VIEW_OWN_RUNS) and run.created_by == user.user_id


async def _visible_run(run_id: str, user: User, container: Container) -> Run:
    """404 both when the run does not exist and when it belongs to someone
    else, so run ids cannot be probed."""
    assert container.runs is not None
    run = await container.runs.get(run_id)
    if run is None or not _can_see(user, run):
        raise HTTPException(status_code=404, detail="run not found")
    return run


def _ready(container: Container) -> None:
    if container.run_manager is None or container.orchestrator is None or container.runs is None:
        raise HTTPException(status_code=503, detail="runs are not configured")


@router.post("/runs", status_code=202)
async def start_run(
    body: StartRunRequest,
    user: User = Depends(_can_start),
    container: Container = Depends(get_container),
) -> dict[str, str]:
    """Starts the workflow in the background and returns at once; follow
    progress at GET /runs/{id}/events."""
    _ready(container)
    if container.ask_limiter is not None and not container.ask_limiter.allow(f"run:{user.user_id}"):
        raise HTTPException(status_code=429, detail="too many runs, slow down")
    symptom = _CONTROL_CHARS.sub("", body.symptom).strip()
    if len(symptom) < 5:
        raise HTTPException(status_code=422, detail="symptom is empty after cleaning")
    run_id = await container.run_manager.submit(symptom, user.user_id)  # type: ignore[union-attr]
    return {"run_id": run_id}


@router.get("/runs")
async def list_runs(
    user: User = Depends(current_user), container: Container = Depends(get_container)
) -> list[dict[str, Any]]:
    _ready(container)
    everyone = has_permission(user.role, Permission.VIEW_ALL_RUNS)
    found = await container.runs.list_runs(  # type: ignore[union-attr]
        created_by=None if everyone else user.user_id
    )
    return [_summary(r) for r in found]


@router.get("/approvals")
async def pending_approvals(
    _: User = Depends(_can_decide), container: Container = Depends(get_container)
) -> list[dict[str, Any]]:
    """The supervisor's queue: every run waiting for a human decision, with
    the drafted work order to review."""
    _ready(container)
    pending = await container.runs.list_runs(  # type: ignore[union-attr]
        state=RunState.PENDING_APPROVAL.value
    )
    items = []
    for summary in pending:
        run = await container.runs.get(summary.run_id)  # type: ignore[union-attr]
        wo = await container.orchestrator.work_order_of(run)  # type: ignore[union-attr]
        items.append({**_summary(run), "work_order": _work_order_json(wo)})
    return items


@router.get("/runs/{run_id}")
async def get_run(
    run_id: str, user: User = Depends(current_user), container: Container = Depends(get_container)
) -> dict[str, Any]:
    _ready(container)
    run = await _visible_run(run_id, user, container)
    wo = await container.orchestrator.work_order_of(run)  # type: ignore[union-attr]
    return {
        **_summary(run),
        "running": container.run_manager.is_running(run_id),  # type: ignore[union-attr]
        "step_count": len(run.steps),
        "work_order": _work_order_json(wo),
    }


@router.get("/runs/{run_id}/events")
async def run_events(
    run_id: str, user: User = Depends(current_user), container: Container = Depends(get_container)
) -> StreamingResponse:
    """SSE progress for one run. A run this process never saw (for example
    after a restart) yields its persisted state and closes."""
    _ready(container)
    run = await _visible_run(run_id, user, container)
    live = await container.run_manager.events(run_id)  # type: ignore[union-attr]

    async def stream() -> AsyncIterator[bytes]:
        if live is None:
            snapshot = {"run_id": run_id, "state": run.state.value, "event": "stream_end"}
            yield f"event: stream_end\ndata: {json.dumps(snapshot)}\n\n".encode()
            return
        async for event in live:
            yield f"event: {event['event']}\ndata: {json.dumps(event)}\n\n".encode()

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"},
    )


@router.post("/runs/{run_id}/cancel")
async def cancel_run(
    run_id: str, user: User = Depends(_can_start), container: Container = Depends(get_container)
) -> dict[str, str]:
    """Server-side cancellation: the background task is cancelled, the
    in-flight model call is abandoned, and the run is closed as failed."""
    _ready(container)
    run = await _visible_run(run_id, user, container)
    if run.created_by != user.user_id:
        raise HTTPException(status_code=404, detail="run not found")
    if not container.run_manager.cancel(run_id):  # type: ignore[union-attr]
        raise HTTPException(status_code=409, detail="run is not running")
    return {"run_id": run_id, "status": "cancelling"}


@router.post("/runs/{run_id}/decision")
async def decide(
    run_id: str,
    body: DecisionRequest,
    user: User = Depends(_can_decide),
    container: Container = Depends(get_container),
) -> dict[str, Any]:
    """Human approval gate. Only a supervisor may call this, never for a run
    they raised themselves (separation of duties), and dispatch happens only
    as a consequence of an approval recorded here."""
    _ready(container)
    run = await _visible_run(run_id, user, container)
    if run.created_by == user.user_id:
        raise PermissionDeniedError("cannot decide a run you raised")
    done = await container.orchestrator.decide(  # type: ignore[union-attr]
        run_id,
        reviewer=user.username,
        decision=body.decision,
        comment=_CONTROL_CHARS.sub("", body.comment),
        edits=body.edits,
    )
    wo = await container.orchestrator.work_order_of(done)  # type: ignore[union-attr]
    return {**_summary(done), "work_order": _work_order_json(wo)}


@router.get("/runs/{run_id}/trace")
async def trace(
    run_id: str, user: User = Depends(current_user), container: Container = Depends(get_container)
) -> dict[str, Any]:
    """The full audit record with the hash chain and whether it verifies."""
    _ready(container)
    run = await _visible_run(run_id, user, container)
    return {
        **_summary(run),
        "chain_valid": run.verify_chain(),
        "steps": [
            {
                "step_index": s.step_index,
                "name": s.name,
                "agent": s.agent_name,
                "provider": s.provider_used,
                "status": s.status,
                "input": s.input_snapshot,
                "output": s.output_snapshot,
                "input_tokens": s.input_tokens,
                "output_tokens": s.output_tokens,
                "started_at": s.started_at.isoformat(),
                "finished_at": s.finished_at.isoformat(),
                "step_hash": s.step_hash,
            }
            for s in run.steps
        ],
    }


@router.get("/runs/{run_id}/replay")
async def replay(
    run_id: str, user: User = Depends(_can_replay), container: Container = Depends(get_container)
) -> dict[str, Any]:
    """T4: plays back the recorded steps. Never calls a model or a tool, and
    refuses (409) a run whose log fails verification."""
    _ready(container)
    run = await _visible_run(run_id, user, container)
    frames = [f.__dict__ for f in replay_run(run)]
    return {**_summary(run), "frames": frames}
