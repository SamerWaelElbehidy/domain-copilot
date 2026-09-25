import asyncio
import json
import time

import pytest
from starlette.testclient import TestClient

from api.rate_limit import TokenBucketLimiter
from api.run_manager import RunManager
from application.llm_recording import RecordingLLMProvider
from domain.value_objects.role import Role
from tests.api.test_auth_and_security import Stack, make_settings
from tests.fakes.in_memory import InMemoryLLMCallRepository
from tests.fakes.world import World, build_world
from tests.unit.agents.test_orchestrator import (
    SYMPTOM,
    happy_script,
    make_orchestrator,
)


class RunStack(Stack):
    def __init__(self, scripted: bool = True, runs_per_minute: int = 100) -> None:
        super().__init__(make_settings(max_body_bytes=100_000))
        self.world: World = build_world()
        if scripted:
            self.world.llm._responses.extend(happy_script(self.world))
        self.manager = RunManager()
        self.orchestrator, self.runs = make_orchestrator(self.world, emit=self.manager.publish)
        self.manager.bind(self.orchestrator)
        self.container.runs = self.runs
        self.container.orchestrator = self.orchestrator
        self.container.run_manager = self.manager
        self.container.ask_limiter = TokenBucketLimiter(runs_per_minute)
        for name, role in [
            ("tech1", Role.TECHNICIAN), ("tech2", Role.TECHNICIAN),
            ("super1", Role.SUPERVISOR), ("admin1", Role.ADMIN),
        ]:
            self.add_user(name, role)
        # One event loop for the whole test, so background run tasks survive
        # between requests exactly as they do under uvicorn.
        self.client = TestClient(self.app, raise_server_exceptions=False)
        self.client.__enter__()

    def close(self) -> None:
        self.client.__exit__(None, None, None)

    def start(self, who="tech1", symptom=SYMPTOM):
        return self.client.post("/runs", json={"symptom": symptom}, headers=self.auth(who))

    def wait(self, run_id, who="tech1", until=("pending_approval",), timeout=10.0):
        deadline = time.time() + timeout
        while time.time() < deadline:
            body = self.client.get(f"/runs/{run_id}", headers=self.auth(who)).json()
            if body["state"] in until and not body["running"]:
                return body
            time.sleep(0.05)
        raise AssertionError(f"run did not reach {until}: {body}")

    def decide(self, run_id, who="super1", **body):
        body.setdefault("decision", "approve")
        return self.client.post(f"/runs/{run_id}/decision", json=body, headers=self.auth(who))


@pytest.fixture
def stack():
    s = RunStack()
    yield s
    s.close()


def pending(stack: RunStack) -> str:
    run_id = stack.start().json()["run_id"]
    stack.wait(run_id)
    return run_id


def test_starting_a_run_returns_at_once_and_reaches_pending_approval(stack):
    response = stack.start()

    assert response.status_code == 202
    run_id = response.json()["run_id"]
    body = stack.wait(run_id)
    assert body["state"] == "pending_approval" and body["equipment_id"]
    assert body["work_order"]["status"] == "pending_approval"
    assert len(body["work_order"]["safety_checklist"]) == 13


def test_a_technician_sees_only_their_own_runs_but_a_supervisor_sees_all(stack):
    run_id = pending(stack)

    assert stack.client.get(f"/runs/{run_id}", headers=stack.auth("tech2")).status_code == 404
    assert stack.client.get("/runs", headers=stack.auth("tech2")).json() == []
    assert stack.client.get(f"/runs/{run_id}", headers=stack.auth("super1")).status_code == 200
    assert len(stack.client.get("/runs", headers=stack.auth("super1")).json()) == 1


def test_only_a_supervisor_can_see_the_approval_queue_and_decide(stack):
    run_id = pending(stack)

    assert stack.client.get("/approvals", headers=stack.auth("tech1")).status_code == 403
    assert stack.client.get("/approvals", headers=stack.auth("admin1")).status_code == 403
    queue = stack.client.get("/approvals", headers=stack.auth("super1")).json()
    assert [q["run_id"] for q in queue] == [run_id]
    assert queue[0]["work_order"]["diagnostic_steps"]
    assert stack.decide(run_id, "tech1").status_code == 403
    assert stack.decide(run_id, "admin1").status_code == 403


def test_approval_dispatches_and_records_who_approved(stack):
    run_id = pending(stack)

    response = stack.decide(run_id, comment="checked on site")

    assert response.status_code == 200
    body = response.json()
    assert body["state"] == "dispatched"
    assert body["work_order"]["status"] == "dispatched"
    assert body["work_order"]["approved_by"] == "super1"
    trace = stack.client.get(f"/runs/{run_id}/trace", headers=stack.auth("tech1")).json()
    names = [s["name"] for s in trace["steps"]]
    assert names[-2:] == ["human_decision", "dispatch"]
    assert trace["chain_valid"] is True


def test_rejection_ends_the_run_and_nothing_is_dispatched(stack):
    run_id = pending(stack)

    body = stack.decide(run_id, decision="reject", comment="wrong machine").json()

    assert body["state"] == "rejected"
    assert body["work_order"]["status"] == "rejected"


def test_a_decided_run_cannot_be_decided_again(stack):
    run_id = pending(stack)
    stack.decide(run_id)

    assert stack.decide(run_id, decision="reject").status_code == 409


def test_the_requester_cannot_approve_their_own_work_order(stack):
    run_id = pending(stack)
    supervisor = stack.users.records["u-super1"].user
    stack.runs.runs[run_id].created_by = supervisor.user_id

    response = stack.decide(run_id, "super1")

    assert response.status_code == 403
    assert stack.runs.runs[run_id].state.value == "pending_approval"


def test_a_reviewer_may_add_safety_steps_but_never_remove_them(stack):
    run_id = pending(stack)
    work_order = stack.client.get(f"/runs/{run_id}", headers=stack.auth("tech1")).json()[
        "work_order"
    ]
    kept = work_order["safety_checklist"]

    removed = stack.decide(
        run_id, decision="edit_and_approve", edits={"safety_checklist": kept[1:]}
    )
    added = stack.decide(
        run_id, decision="edit_and_approve",
        edits={"safety_checklist": kept + ["Confirm the area is clear"]},
    )

    assert removed.status_code == 422
    assert added.status_code == 200
    assert "Confirm the area is clear" in added.json()["work_order"]["safety_checklist"]


def test_unknown_decision_values_are_rejected(stack):
    run_id = pending(stack)

    assert stack.decide(run_id, decision="yolo").status_code == 422


def test_replay_returns_the_recorded_steps_and_never_calls_the_model(stack):
    run_id = pending(stack)
    calls_before = len(stack.world.llm.received_messages)

    first = stack.client.get(f"/runs/{run_id}/replay", headers=stack.auth("super1")).json()
    second = stack.client.get(f"/runs/{run_id}/replay", headers=stack.auth("admin1")).json()

    assert first["frames"] == second["frames"]
    assert [f["name"] for f in first["frames"]][0] == "receive"
    assert len(stack.world.llm.received_messages) == calls_before
    denied = stack.client.get(f"/runs/{run_id}/replay", headers=stack.auth("tech1"))
    assert denied.status_code == 403


def test_a_tampered_log_is_reported_and_replay_refuses_it(stack):
    run_id = pending(stack)
    stack.runs.runs[run_id].steps[1].output_snapshot["result"] = {"equipment_id": "eq-forged"}

    trace = stack.client.get(f"/runs/{run_id}/trace", headers=stack.auth("super1")).json()
    replay = stack.client.get(f"/runs/{run_id}/replay", headers=stack.auth("super1"))

    assert trace["chain_valid"] is False
    assert replay.status_code == 409


def test_progress_events_stream_and_end_with_stream_end(stack):
    run_id = pending(stack)

    response = stack.client.get(f"/runs/{run_id}/events", headers=stack.auth("tech1"))

    assert response.headers["content-type"].startswith("text/event-stream")
    kinds = [
        line[len("event: "):] for line in response.text.splitlines() if line.startswith("event: ")
    ]
    assert kinds[0] == "step_started" and "awaiting_approval" in kinds
    assert kinds[-1] == "stream_end"


def test_events_of_someone_elses_run_are_hidden(stack):
    run_id = pending(stack)

    other = stack.client.get(f"/runs/{run_id}/events", headers=stack.auth("tech2"))
    assert other.status_code == 404


def test_cancelling_stops_the_run_and_closes_it_as_failed():
    stack = RunStack(scripted=False)
    try:
        async def never_finishes(*_a, **_k):
            await asyncio.sleep(60)

        stack.world.llm.complete = never_finishes
        run_id = stack.start().json()["run_id"]

        assert stack.client.post(
            f"/runs/{run_id}/cancel", headers=stack.auth("tech2")
        ).status_code == 404
        assert stack.client.post(
            f"/runs/{run_id}/cancel", headers=stack.auth("tech1")
        ).status_code == 200

        body = stack.wait(run_id, until=("failed",))
        trace = stack.client.get(f"/runs/{run_id}/trace", headers=stack.auth("tech1")).json()
        assert body["running"] is False
        assert trace["steps"][-1]["output"]["reason"] == "cancelled by client"
        assert trace["chain_valid"] is True
        assert stack.client.post(
            f"/runs/{run_id}/cancel", headers=stack.auth("tech1")
        ).status_code == 409
    finally:
        stack.close()


def test_input_validation_auth_and_rate_limit():
    stack = RunStack(runs_per_minute=1)
    try:
        assert stack.client.post("/runs", json={"symptom": SYMPTOM}).status_code == 401
        assert stack.start(symptom="hi").status_code == 422
        assert stack.start("super1").status_code == 403
        assert stack.start().status_code == 202
        assert stack.start().status_code == 429
    finally:
        stack.close()


def test_personal_data_in_a_symptom_is_redacted_in_the_audit_log_too(stack):
    response = stack.start(symptom=SYMPTOM + ", contact ali@example.com or 01012345678")
    run_id = response.json()["run_id"]
    stack.wait(run_id)

    assert response.json()["redactions"] == {"EMAIL": 1, "PHONE": 1}
    trace = stack.client.get(f"/runs/{run_id}/trace", headers=stack.auth("tech1")).json()
    assert "ali@example.com" not in json.dumps(trace) and "01012345678" not in json.dumps(trace)
    assert "[EMAIL]" in trace["steps"][0]["input"]["symptom"]


def test_a_decision_comment_is_redacted_before_it_is_recorded(stack):
    run_id = pending(stack)

    stack.decide(run_id, comment="checked, call 01012345678 if wrong")

    trace = stack.client.get(f"/runs/{run_id}/trace", headers=stack.auth("super1")).json()
    decision = next(s for s in trace["steps"] if s["name"] == "human_decision")
    assert "01012345678" not in json.dumps(decision) and "[PHONE]" in decision["input"]["comment"]


class RecordedRunStack(RunStack):
    """The workflow's model calls go through the recording decorator, as they
    do in production."""

    def __init__(self):
        Stack.__init__(self, make_settings(max_body_bytes=100_000))
        self.world = build_world()
        self.world.llm._responses.extend(happy_script(self.world))
        self.calls = InMemoryLLMCallRepository()
        self.world.llm = RecordingLLMProvider(self.world.llm, self.calls, provider_name="fake")
        self.manager = RunManager()
        self.orchestrator, self.runs = make_orchestrator(self.world, emit=self.manager.publish)
        self.manager.bind(self.orchestrator)
        self.container.runs, self.container.orchestrator = self.runs, self.orchestrator
        self.container.run_manager, self.container.llm_calls = self.manager, self.calls
        self.container.ask_limiter = TokenBucketLimiter(100)
        for name, role in [("tech1", Role.TECHNICIAN), ("super1", Role.SUPERVISOR)]:
            self.add_user(name, role)
        self.client = TestClient(self.app, raise_server_exceptions=False)
        self.client.__enter__()


def test_every_model_call_of_a_run_is_attributed_and_linked_by_correlation_id():
    stack = RecordedRunStack()
    try:
        response = stack.start()
        run_id = response.json()["run_id"]
        stack.wait(run_id)

        trace = stack.client.get(f"/runs/{run_id}/trace", headers=stack.auth("tech1")).json()

        calls = asyncio.run(stack.calls.calls_for_run(run_id))
        assert calls and all(c.user_id == "u-tech1" and c.purpose == "run" for c in calls)
        correlation_id = trace["steps"][0]["input"]["correlation_id"]
        assert correlation_id != "-" and {c.correlation_id for c in calls} == {correlation_id}
        assert trace["usage"]["calls"] == len(calls)
        assert trace["usage"]["input_tokens"] == sum(c.input_tokens for c in calls)
    finally:
        stack.close()
