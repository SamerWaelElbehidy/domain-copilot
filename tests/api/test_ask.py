import asyncio
import json

import pytest

from api.rate_limit import TokenBucketLimiter
from application.llm_recording import RecordingLLMProvider
from application.ports.llm_provider import ProviderUnavailableError
from application.use_cases.answer_question import GroundedAnswerer
from config.prompts import load_prompt
from domain.value_objects.role import Role
from tests.api.test_auth_and_security import Stack, make_settings
from tests.fakes.in_memory import InMemoryChatSessionRepository, InMemoryLLMCallRepository
from tests.fakes.world import build_world, say

ROUTER = "eq-cnc-router-dwr2200"
QUESTION = "What must be checked on the dust extraction hose connection before every job?"
GOOD = json.dumps({"answer": "The hose must be fully seated.", "citations": [1]})


class AskStack(Stack):
    def __init__(self, scripted, ask_per_minute: int = 100) -> None:
        super().__init__(make_settings(max_body_bytes=100_000))
        self.world = build_world(scripted)
        self.calls = InMemoryLLMCallRepository()
        llm = RecordingLLMProvider(self.world.llm, self.calls, provider_name="fake")
        self.container.answerer = GroundedAnswerer(
            llm=llm,
            vector_store=self.world.vector_store,
            keyword_index=self.world.keyword_index,
            document_repository=self.world.documents,
            system_prompt=load_prompt("answer_question", "v3").text,
            min_dense_score=0.0,
            min_support=0.0,
        )
        self.container.sessions = InMemoryChatSessionRepository()
        self.container.llm_calls = self.calls
        self.container.ask_limiter = TokenBucketLimiter(ask_per_minute)
        self.add_user("tech1", Role.TECHNICIAN)
        self.add_user("tech2", Role.TECHNICIAN)
        self.add_user("admin1", Role.ADMIN)

    def ask(self, who="tech1", **body):
        body.setdefault("question", QUESTION)
        body.setdefault("equipment_id", ROUTER)
        return self.client.post("/ask", json=body, headers=self.auth(who))


def test_a_grounded_answer_has_citations_and_creates_a_session():
    s = AskStack([say(GOOD)])

    response = s.ask()

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "answered" and body["citations"]
    stored = s.container.sessions.messages[body["session_id"]]
    assert [m.role for m in stored] == ["user", "assistant"]
    assert stored[1].citations == body["citations"]


def test_a_refusal_is_a_normal_answer_and_is_stored_with_its_reason():
    s = AskStack([say(json.dumps({"insufficient": True}))])

    body = s.ask().json()

    assert body["status"] == "refused" and body["reason"]
    stored = s.container.sessions.messages[body["session_id"]]
    assert stored[1].status == "refused"


def test_another_users_session_looks_exactly_like_a_missing_one():
    s = AskStack([say(GOOD), say(GOOD)])
    session_id = s.ask("tech1").json()["session_id"]

    other = s.ask("tech2", session_id=session_id)
    missing = s.ask("tech2", session_id="s-does-not-exist")

    assert other.status_code == missing.status_code == 404
    assert other.json()["detail"] == missing.json()["detail"]
    assert s.client.get(f"/sessions/{session_id}", headers=s.auth("tech2")).status_code == 404
    assert s.client.get(f"/sessions/{session_id}", headers=s.auth("tech1")).status_code == 200


def test_history_lists_only_the_callers_sessions():
    s = AskStack([say(GOOD), say(GOOD)])
    s.ask("tech1")
    s.ask("tech2")

    mine = s.client.get("/sessions", headers=s.auth("tech1")).json()

    assert len(mine) == 1


@pytest.mark.parametrize("question", ["hi", "x" * 1001])
def test_question_length_is_validated(question):
    s = AskStack([])

    assert s.ask(question=question).status_code == 422


def test_control_characters_are_stripped_before_use():
    s = AskStack([say(GOOD)])

    body = s.ask(question="\x00\x07" + QUESTION + "\x1b").json()

    user_message = s.container.sessions.messages[body["session_id"]][0]
    assert user_message.content == QUESTION


def test_a_control_character_only_question_is_rejected():
    s = AskStack([])

    assert s.ask(question="\x00\x01\x02\x03\x04").status_code == 422


def test_asking_requires_authentication():
    s = AskStack([])

    assert s.client.post("/ask", json={"question": QUESTION}).status_code == 401


def test_the_per_user_ask_limit_returns_429_without_calling_the_model():
    s = AskStack([say(GOOD)], ask_per_minute=1)

    assert s.ask().status_code == 200
    calls_before = len(s.world.llm.received_messages)
    assert s.ask().status_code == 429
    assert len(s.world.llm.received_messages) == calls_before


def test_the_stream_emits_events_in_order_and_ends_with_a_validated_answer():
    s = AskStack([say(GOOD)])

    response = s.client.post(
        "/ask/stream", json={"question": QUESTION, "equipment_id": ROUTER}, headers=s.auth("tech1")
    )

    assert response.headers["content-type"].startswith("text/event-stream")
    events = [
        json.loads(line[len("data: "):])
        for line in response.text.splitlines()
        if line.startswith("data: ")
    ]
    kinds = [e["type"] for e in events]
    assert kinds[0] == "session" and kinds[1] == "retrieval" and kinds[-1] == "answer"
    assert "token" in kinds
    assert events[-1]["answer"]["status"] == "answered"
    session_id = events[0]["session_id"]
    assert s.container.sessions.messages[session_id][-1].role == "assistant"


def test_usage_is_admin_only_and_attributes_calls_to_the_user():
    s = AskStack([say(GOOD)])
    s.ask("tech1")

    assert s.client.get("/usage", headers=s.auth("tech1")).status_code == 403
    rows = s.client.get("/usage", headers=s.auth("admin1")).json()

    assert [r["user_id"] for r in rows] == ["u-tech1"]
    assert rows[0]["calls"] >= 1


def test_the_correlation_id_links_the_response_to_the_recorded_model_calls():
    s = AskStack([say(GOOD)])

    response = s.ask()

    correlation_id = response.json()["correlation_id"]
    assert correlation_id == response.headers["x-request-id"]
    linked = asyncio.run(s.calls.calls_for_correlation(correlation_id))
    assert linked and all(c.user_id == "u-tech1" for c in linked)


def test_closing_the_stream_early_closes_the_provider_stream():
    s = AskStack([say("one two three four five six seven eight")])
    answerer = s.container.answerer

    async def consume_one_token_then_disconnect():
        stream = answerer.answer_stream(QUESTION, ROUTER)
        async for event in stream:
            if event["type"] == "token":
                break
        await stream.aclose()

    asyncio.run(consume_one_token_then_disconnect())

    assert s.world.llm.stream_closed_early is True


def test_personal_data_is_redacted_before_storage_and_before_the_model_sees_it():
    s = AskStack([say(GOOD)])
    question = QUESTION + " Call me on 01012345678 or ali@example.com, id 29001011234567"

    body = s.ask(question=question).json()

    assert body["redactions"] == {"EMAIL": 1, "NATIONAL_ID": 1, "PHONE": 1}
    stored = s.container.sessions.messages[body["session_id"]][0].content
    sent_to_model = json.dumps(
        [[m.content for m in call] for call in s.world.llm.received_messages]
    )
    for leaked in ("01012345678", "ali@example.com", "29001011234567"):
        assert leaked not in stored and leaked not in sent_to_model
    assert "[PHONE]" in stored


def _model_down(stack):
    async def down(*_args, **_kwargs):
        raise ProviderUnavailableError("ollama: ReadTimeout")

    stack.world.llm.complete = down


def test_a_model_outage_is_a_503_with_a_retry_hint_and_no_internal_detail():
    s = AskStack([])
    _model_down(s)

    response = s.ask()

    assert response.status_code == 503 and response.headers["retry-after"] == "10"
    assert "try again" in response.json()["detail"]
    assert "ollama" not in response.text and "ReadTimeout" not in response.text


def test_a_model_outage_during_streaming_is_reported_as_an_error_event():
    s = AskStack([])
    _model_down(s)

    response = s.client.post(
        "/ask/stream", json={"question": QUESTION, "equipment_id": ROUTER}, headers=s.auth("tech1")
    )

    events = [
        json.loads(line[len("data: "):])
        for line in response.text.splitlines()
        if line.startswith("data: ")
    ]
    assert events[-1]["type"] == "error" and "try again" in events[-1]["detail"]
    assert "ReadTimeout" not in response.text
