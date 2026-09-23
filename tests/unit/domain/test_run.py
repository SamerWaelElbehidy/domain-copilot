from dataclasses import replace
from datetime import datetime

import pytest

from domain.entities.run import Run
from domain.errors.domain_errors import InvalidRunTransitionError, TamperedRunError
from domain.value_objects.run_state import RunState
from domain.value_objects.run_step import RunStep


def make_run() -> Run:
    return Run(run_id="run-1", equipment_id="eq-cnc-router-01", started_at=datetime(2026, 1, 1))


def make_step(run: Run, step_index: int, name: str, output: dict) -> RunStep:
    return RunStep.create(
        step_index=step_index,
        name=name,
        agent_name="symptom-matcher",
        provider_used="ollama",
        input_snapshot={"symptom": "spindle overheating"},
        output_snapshot=output,
        input_tokens=10,
        output_tokens=5,
        started_at=datetime(2026, 1, 1, 0, 0, step_index),
        finished_at=datetime(2026, 1, 1, 0, 1, step_index),
        status="success",
        previous_hash=run.last_step_hash,
    )


def test_valid_transition_sequence_reaches_pending_approval():
    run = make_run()

    run.transition_to(RunState.MATCHING_SYMPTOM)
    run.transition_to(RunState.DIAGNOSING)
    run.transition_to(RunState.DRAFTING_WORK_ORDER)
    run.transition_to(RunState.PENDING_APPROVAL)

    assert run.state == RunState.PENDING_APPROVAL
    assert not run.is_terminal


def test_illegal_transition_is_rejected():
    run = make_run()

    with pytest.raises(InvalidRunTransitionError):
        run.transition_to(RunState.DISPATCHED)


def test_terminal_states_have_no_outgoing_transitions():
    run = make_run()
    run.transition_to(RunState.REFUSED_LOW_EVIDENCE)

    assert run.is_terminal
    with pytest.raises(InvalidRunTransitionError):
        run.transition_to(RunState.MATCHING_SYMPTOM)


def test_record_step_chains_hashes_and_verifies():
    run = make_run()
    step0 = make_step(run, 0, "match_symptom", {"equipment_id": "eq-cnc-router-01"})
    run.record_step(step0)
    step1 = make_step(run, 1, "diagnose", {"diagnostic_steps": ["check coolant flow"]})
    run.record_step(step1)

    assert len(run.steps) == 2
    assert run.verify_chain() is True


def test_out_of_order_step_index_is_rejected():
    run = make_run()
    bad_step = make_step(run, 5, "match_symptom", {"equipment_id": "eq-cnc-router-01"})

    with pytest.raises(InvalidRunTransitionError):
        run.record_step(bad_step)


def test_recording_a_step_with_a_forged_hash_is_rejected():
    run = make_run()
    step0 = make_step(run, 0, "match_symptom", {"equipment_id": "eq-cnc-router-01"})
    forged = replace(step0, step_hash="0" * 64)

    with pytest.raises(TamperedRunError):
        run.record_step(forged)


def test_tampering_a_stored_step_after_the_fact_fails_verification():
    run = make_run()
    run.record_step(make_step(run, 0, "match_symptom", {"equipment_id": "eq-cnc-router-01"}))
    run.record_step(make_step(run, 1, "diagnose", {"diagnostic_steps": ["check coolant flow"]}))
    assert run.verify_chain() is True

    tampered_step = replace(run.steps[0], output_snapshot={"equipment_id": "eq-WRONG-equipment"})
    run.steps[0] = tampered_step

    assert run.verify_chain() is False
