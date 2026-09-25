import asyncio
import json

import pytest

from application.agents.diagnostic_planner import DiagnosticSafetyPlanner
from application.agents.symptom_matcher import SymptomMatcher
from application.agents.work_order_generator import WorkOrderGenerator
from application.ports.llm_provider import CompletionResult
from application.use_cases.orchestrator import CopilotOrchestrator, StepPolicy
from application.use_cases.replay_run import replay_run
from config.prompts import load_prompt
from domain.entities.work_order import WorkOrderStatus
from domain.errors.domain_errors import (
    InvalidReviewEditError,
    InvalidRunTransitionError,
    StepFailedError,
    TamperedRunError,
)
from domain.value_objects.run_state import RunState
from tests.fakes.fake_llm_provider import FakeLLMProvider
from tests.fakes.in_memory import InMemoryRunRepository
from tests.fakes.world import World, build_world, call_tool, say

ROUTER = "eq-cnc-router-dwr2200"
SYMPTOM = "spindle overheating during long runs"
NO_WAIT = StepPolicy(timeout_seconds=5, max_attempts=3, backoff_base_seconds=0.5)


def run(coro):
    return asyncio.run(coro)


def happy_script(world_for_ids: World) -> list[CompletionResult]:
    diag_id = world_for_ids.chunk_id(
        "doc-cnc-router-dwr2200-rev-c", "diagnostic", "spindle overheating"
    )
    steps = [{"text": "Check the spindle air-cooling intake.", "chunk_id": diag_id}]
    return [
        call_tool("search_manual_chunks", {"query": "spindle overheating", "top_k": 5}),
        say(json.dumps({"equipment_id": ROUTER})),
        say(json.dumps({"steps": steps})),
        say(json.dumps({"summary": "Spindle overheats on long runs."})),
    ]


def make_orchestrator(
    world: World, sleeps=None, fallback=None, policy=NO_WAIT, emit=None, prompt_versions=None
):
    async def fake_sleep(seconds: float) -> None:
        if sleeps is not None:
            sleeps.append(seconds)

    runs = InMemoryRunRepository()
    orchestrator = CopilotOrchestrator(
        matcher=SymptomMatcher(
            llm=world.llm,
            registry=world.registry,
            document_repository=world.documents,
            system_prompt=load_prompt("symptom_matcher").text,
        ),
        planner=DiagnosticSafetyPlanner(
            llm=world.llm,
            registry=world.registry,
            system_prompt=load_prompt("diagnostic_planner").text,
        ),
        generator=WorkOrderGenerator(
            llm=world.llm,
            registry=world.registry,
            system_prompt=load_prompt("work_order_generator").text,
        ),
        registry=world.registry,
        run_repository=runs,
        work_order_repository=world.work_orders,
        policy=policy,
        fallback=fallback,
        sleep=fake_sleep,
        emit=emit,
        prompt_versions=prompt_versions,
    )
    return orchestrator, runs


def scripted_world() -> World:
    world = build_world()
    world.llm._responses.extend(happy_script(world))
    return world


def start_happy():
    world = scripted_world()
    orchestrator, runs = make_orchestrator(world)
    return world, orchestrator, runs, run(orchestrator.start(SYMPTOM))


# --- happy path and the approval gate ----------------------------------------


def test_workflow_runs_to_pending_approval_and_records_a_verifiable_trail():
    world, _, _, result = start_happy()

    assert result.state == RunState.PENDING_APPROVAL
    assert result.equipment_id == ROUTER
    assert [s.name for s in result.steps] == [
        "receive", "match_symptom", "diagnose", "draft_work_order", "await_approval",
    ]
    assert result.verify_chain()
    (work_order,) = world.work_orders.work_orders.values()
    assert work_order.status == WorkOrderStatus.PENDING_APPROVAL
    assert len(work_order.safety_checklist) == 13


def test_nothing_is_dispatched_until_a_human_approves():
    world, _, _, result = start_happy()

    (work_order,) = world.work_orders.work_orders.values()
    assert work_order.status != WorkOrderStatus.DISPATCHED
    assert "dispatch" not in [s.name for s in result.steps]


def test_approval_dispatches_and_audits_the_human_decision():
    world, orchestrator, _, started = start_happy()

    done = run(
        orchestrator.decide(started.run_id, reviewer="supervisor-1", decision="approve",
                            comment="Looks right")
    )

    assert done.state == RunState.DISPATCHED
    (work_order,) = world.work_orders.work_orders.values()
    assert work_order.status == WorkOrderStatus.DISPATCHED
    assert work_order.approved_by == "supervisor-1"
    decision_step = next(s for s in done.steps if s.name == "human_decision")
    assert decision_step.input_snapshot["reviewer"] == "supervisor-1"
    assert decision_step.input_snapshot["comment"] == "Looks right"
    assert done.steps[-1].name == "dispatch"
    assert done.verify_chain()


def test_rejection_ends_the_run_and_never_dispatches():
    world, orchestrator, _, started = start_happy()

    done = run(orchestrator.decide(started.run_id, reviewer="supervisor-1", decision="reject"))

    assert done.state == RunState.REJECTED
    (work_order,) = world.work_orders.work_orders.values()
    assert work_order.status == WorkOrderStatus.REJECTED
    assert "dispatch" not in [s.name for s in done.steps]


def test_edit_and_approve_records_the_edit_before_approval():
    world, orchestrator, _, started = start_happy()
    original = list(next(iter(world.work_orders.work_orders.values())).safety_checklist)

    done = run(
        orchestrator.decide(
            started.run_id,
            reviewer="supervisor-1",
            decision="edit_and_approve",
            edits={
                "diagnostic_steps": ["Check intake, then log the shop temperature."],
                "safety_checklist": [*original, "Notify the shift lead before restart."],
            },
        )
    )

    names = [s.name for s in done.steps]
    assert names.index("reviewer_edit") < names.index("human_decision")
    (work_order,) = world.work_orders.work_orders.values()
    assert work_order.safety_checklist[-1] == "Notify the shift lead before restart."
    assert done.state == RunState.DISPATCHED


def test_a_reviewer_cannot_remove_a_safety_step():
    world, orchestrator, runs, started = start_happy()
    original = list(next(iter(world.work_orders.work_orders.values())).safety_checklist)

    with pytest.raises(InvalidReviewEditError):
        run(
            orchestrator.decide(
                started.run_id, reviewer="supervisor-1", decision="edit_and_approve",
                edits={"safety_checklist": original[:-1]},
            )
        )

    assert run(runs.get(started.run_id)).state == RunState.PENDING_APPROVAL
    (work_order,) = world.work_orders.work_orders.values()
    assert work_order.status == WorkOrderStatus.PENDING_APPROVAL


def test_deciding_twice_is_refused():
    _, orchestrator, _, started = start_happy()
    run(orchestrator.decide(started.run_id, reviewer="s", decision="approve"))

    with pytest.raises(InvalidRunTransitionError):
        run(orchestrator.decide(started.run_id, reviewer="s", decision="approve"))


# --- refusal ------------------------------------------------------------------


def test_low_evidence_ends_in_a_refusal_with_no_work_order():
    world = build_world([say(json.dumps({"equipment_id": None}))])
    orchestrator, _ = make_orchestrator(world)

    result = run(orchestrator.start("the canteen lights flicker"))

    assert result.state == RunState.REFUSED_LOW_EVIDENCE
    assert world.work_orders.work_orders == {}
    assert result.steps[-1].status == "refused"
    assert result.verify_chain()


# --- FR-5: retry, timeout, degradation, cancellation --------------------------


def test_malformed_model_output_is_retried_with_exponential_backoff():
    world = build_world()
    good = happy_script(world)
    world.llm._responses.extend([say("not json"), say("still not json"), *good])
    sleeps: list[float] = []
    orchestrator, _ = make_orchestrator(world, sleeps=sleeps)

    result = run(orchestrator.start(SYMPTOM))

    assert result.state == RunState.PENDING_APPROVAL
    statuses = [s.status for s in result.steps if s.name == "match_symptom"]
    assert statuses == ["retried", "retried", "success"]
    assert sleeps == [0.5, 1.0]


def test_exhausted_retries_degrade_to_plain_rag_when_a_fallback_exists():
    world = build_world([say("nope")] * 3)

    async def fallback(question: str) -> dict:
        return {"answer": "See the CNC manual.", "citations": []}

    orchestrator, _ = make_orchestrator(world, fallback=fallback)

    result = run(orchestrator.start(SYMPTOM))

    assert result.state == RunState.DEGRADED_PLAIN_RAG
    assert result.steps[-1].name == "degrade_to_plain_rag"
    assert result.steps[-1].output_snapshot["answer"] == "See the CNC manual."
    assert world.work_orders.work_orders == {}


def test_exhausted_retries_without_a_fallback_fail_the_run_visibly():
    world = build_world([say("nope")] * 3)
    orchestrator, runs = make_orchestrator(world)

    with pytest.raises(StepFailedError):
        run(orchestrator.start(SYMPTOM))

    (stored,) = runs.runs.values()
    assert stored.state == RunState.FAILED
    assert stored.verify_chain()


class SlowLLM(FakeLLMProvider):
    async def complete(self, messages, tools=None, json_mode=False):
        await asyncio.sleep(5)
        return await super().complete(messages, tools, json_mode)


def slow_world() -> World:
    world = build_world()
    slow = SlowLLM(embedding_dim=256)
    world.llm = slow
    return world


def orchestrator_with_llm(world: World, policy: StepPolicy):
    orchestrator, runs = make_orchestrator(world, policy=policy)
    orchestrator._matcher._llm = world.llm
    return orchestrator, runs


def test_a_step_that_exceeds_its_timeout_is_retried_then_fails():
    world = slow_world()
    orchestrator, runs = orchestrator_with_llm(
        world, StepPolicy(timeout_seconds=0.05, max_attempts=2, backoff_base_seconds=0)
    )

    with pytest.raises(StepFailedError):
        run(orchestrator.start(SYMPTOM))

    (stored,) = runs.runs.values()
    errors = [s.output_snapshot.get("error") for s in stored.steps if s.name == "match_symptom"]
    assert errors == ["TimeoutError", "TimeoutError"]


def test_client_cancellation_stops_work_and_closes_the_run():
    world = slow_world()
    orchestrator, runs = orchestrator_with_llm(world, StepPolicy(timeout_seconds=30))

    async def scenario():
        task = asyncio.create_task(orchestrator.start(SYMPTOM))
        await asyncio.sleep(0.05)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    run(scenario())

    (stored,) = runs.runs.values()
    assert stored.state == RunState.FAILED
    assert stored.steps[-1].output_snapshot["reason"] == "cancelled by client"


def test_progress_events_are_emitted_for_a_live_ui():
    world = scripted_world()
    events: list[dict] = []

    async def emit(event: dict) -> None:
        events.append(event)

    orchestrator, _ = make_orchestrator(world, emit=emit)
    run(orchestrator.start(SYMPTOM))

    kinds = [(e["event"], e.get("step")) for e in events]
    assert ("step_started", "match_symptom") in kinds
    assert ("step_finished", "diagnose") in kinds
    assert kinds[-1] == ("awaiting_approval", None)


# --- T4: replay ----------------------------------------------------------------


def test_replay_reproduces_the_recorded_run_exactly_and_never_calls_the_llm():
    world, orchestrator, _, started = start_happy()
    done = run(orchestrator.decide(started.run_id, reviewer="s", decision="approve"))
    calls_before = len(world.llm.received_messages)

    first = list(replay_run(done))
    second = list(replay_run(done))

    assert first == second
    assert [f.name for f in first] == [s.name for s in done.steps]
    assert first[1].output_snapshot == done.steps[1].output_snapshot
    assert len(world.llm.received_messages) == calls_before


def test_replay_refuses_a_run_whose_log_was_edited_after_the_fact():
    from dataclasses import replace

    _, _, _, result = start_happy()
    result.steps[1] = replace(result.steps[1], output_snapshot={"result": {"equipment_id": "x"}})

    with pytest.raises(TamperedRunError):
        list(replay_run(result))


def test_each_agent_step_records_which_prompt_version_produced_it():
    world = scripted_world()
    orchestrator, _ = make_orchestrator(
        world,
        prompt_versions={
            "symptom_matcher": "symptom_matcher.v1@abc123",
            "diagnostic_safety_planner": "diagnostic_planner.v1@def456",
            "work_order_generator": "work_order_generator.v1@789abc",
        },
    )

    result = run(orchestrator.start(SYMPTOM))

    recorded = {s.name: s.input_snapshot["prompt"] for s in result.steps if s.agent_name}
    assert recorded == {
        "match_symptom": "symptom_matcher.v1@abc123",
        "diagnose": "diagnostic_planner.v1@def456",
        "draft_work_order": "work_order_generator.v1@789abc",
    }
