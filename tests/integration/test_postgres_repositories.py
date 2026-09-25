"""Runs the real migrations and the real Postgres adapters against a scratch
database. Needs only Postgres (no Ollama), so CI runs it on every PR; locally it
skips unless Postgres is reachable (docker compose up postgres)."""

import asyncio
import json
import os
import socket
import uuid
from contextlib import asynccontextmanager
from datetime import UTC, date, datetime

import asyncpg
import pytest

from application.ports.chat_session_repository import ChatMessage
from application.ports.llm_call_repository import LLMCall
from domain.entities.equipment import Equipment
from domain.entities.manual_document import ManualDocument
from domain.entities.run import Run
from domain.entities.user import User
from domain.entities.work_order import WorkOrder, WorkOrderStatus
from domain.value_objects.role import Role
from domain.value_objects.run_state import RunState
from domain.value_objects.run_step import RunStep
from infrastructure.persistence.migrations import apply_migrations
from infrastructure.persistence.postgres_chat_session_repository import (
    PostgresChatSessionRepository,
)
from infrastructure.persistence.postgres_document_repository import PostgresDocumentRepository
from infrastructure.persistence.postgres_llm_call_repository import PostgresLLMCallRepository
from infrastructure.persistence.postgres_pool import create_pool
from infrastructure.persistence.postgres_run_repository import PostgresRunRepository
from infrastructure.persistence.postgres_user_repository import PostgresUserRepository
from infrastructure.persistence.postgres_work_order_repository import PostgresWorkOrderRepository

HOST = os.environ.get("POSTGRES_HOST", "localhost")
PORT = int(os.environ.get("POSTGRES_PORT", "5433"))


def _reachable() -> bool:
    try:
        with socket.create_connection((HOST, PORT), timeout=1):
            return True
    except OSError:
        return False


pytestmark = pytest.mark.skipif(not _reachable(), reason="needs Postgres (docker compose up)")
NOW = datetime(2026, 1, 1, 12, tzinfo=UTC)


def run(coro):
    return asyncio.run(coro)


@asynccontextmanager
async def scratch_database():
    """A throwaway database with every migration applied, dropped afterwards."""
    name = f"test_{uuid.uuid4().hex[:10]}"
    admin = await asyncpg.connect(
        user=os.environ.get("POSTGRES_USER", "domain_copilot"),
        password=os.environ.get("POSTGRES_PASSWORD", "domain_copilot_dev"),
        database=os.environ.get("POSTGRES_DB", "domain_copilot"),
        host=HOST,
        port=PORT,
    )
    await admin.execute(f'CREATE DATABASE "{name}"')
    pool = await create_pool(database=name)
    try:
        async with pool.acquire() as conn:
            await apply_migrations(conn)
        yield pool
    finally:
        await pool.close()
        await admin.execute(f'DROP DATABASE "{name}" WITH (FORCE)')
        await admin.close()


async def seed_basics(pool) -> tuple[PostgresUserRepository, PostgresDocumentRepository]:
    users, docs = PostgresUserRepository(pool), PostgresDocumentRepository(pool)
    await users.create(User("u-tech", "tech", Role.TECHNICIAN), "hash")
    await users.create(User("u-sup", "sup", Role.SUPERVISOR), "hash")
    await docs.save_equipment(Equipment("eq-a", "Machine A DWR-1", "DWR-1", "industrial"))
    await docs.save_equipment(Equipment("eq-b", "Machine B", "n/a", "industrial"))
    await docs.save_document(ManualDocument("doc-a", "eq-a", "Rev. A", date(2025, 1, 1), "A"))
    await docs.save_document(
        ManualDocument("doc-a-old", "eq-a", "Rev. 0", date(2024, 1, 1), "Old", status="superseded")
    )
    return users, docs


def test_every_migration_applies_cleanly_and_reapplying_is_a_no_op():
    async def go():
        async with scratch_database() as pool:
            async with pool.acquire() as conn:
                again = await apply_migrations(conn)
                tables = {
                    r["tablename"]
                    for r in await conn.fetch(
                        "SELECT tablename FROM pg_tables WHERE schemaname = 'public'"
                    )
                }
            return again, tables

    again, tables = run(go())

    assert again == []
    assert {"runs", "run_steps", "users", "llm_calls", "chat_messages", "work_orders"} <= tables


def build_run(run_id: str, created_by: str | None) -> Run:
    run = Run(run_id=run_id, equipment_id="eq-a", started_at=NOW, created_by=created_by)
    for index, name in enumerate(["receive", "match_symptom", "diagnose"]):
        run.record_step(
            RunStep.create(
                step_index=index, name=name, agent_name=None, provider_used="ollama",
                input_snapshot={"n": index}, output_snapshot={"result": {"n": index}},
                input_tokens=1, output_tokens=2, started_at=NOW, finished_at=NOW,
                status="success", previous_hash=run.last_step_hash,
            )
        )
    run.state = RunState.PENDING_APPROVAL
    return run


def test_a_run_round_trips_with_its_owner_and_a_valid_hash_chain():
    async def go():
        async with scratch_database() as pool:
            await seed_basics(pool)
            runs = PostgresRunRepository(pool)
            await runs.save(build_run("run-1", "u-tech"))
            await runs.save(build_run("run-2", "u-sup"))
            loaded = await runs.get("run-1")
            return (
                loaded,
                await runs.list_runs(created_by="u-tech"),
                await runs.list_runs(state="pending_approval"),
                await runs.list_runs(state="dispatched"),
            )

    loaded, mine, pending, dispatched = run(go())

    assert loaded.created_by == "u-tech" and loaded.verify_chain()
    assert [r.run_id for r in mine] == ["run-1"]
    assert {r.run_id for r in pending} == {"run-1", "run-2"} and dispatched == []


def test_editing_a_stored_step_is_detected_after_reloading_from_the_database():
    async def go():
        async with scratch_database() as pool:
            await seed_basics(pool)
            runs = PostgresRunRepository(pool)
            await runs.save(build_run("run-1", "u-tech"))
            await pool.execute(
                "UPDATE run_steps SET output_snapshot = $1::jsonb "
                "WHERE run_id = 'run-1' AND step_index = 1",
                json.dumps({"result": {"n": 999}}),
            )
            return await runs.get("run-1")

    assert run(go()).verify_chain() is False


def test_resaving_a_run_appends_new_steps_and_never_rewrites_old_ones():
    async def go():
        async with scratch_database() as pool:
            await seed_basics(pool)
            runs = PostgresRunRepository(pool)
            first = build_run("run-1", "u-tech")
            await runs.save(first)
            first.record_step(
                RunStep.create(
                    step_index=3, name="await_approval", agent_name=None, provider_used=None,
                    input_snapshot={}, output_snapshot={"status": "pending"}, input_tokens=0,
                    output_tokens=0, started_at=NOW, finished_at=NOW, status="success",
                    previous_hash=first.last_step_hash,
                )
            )
            await runs.save(first)
            return await runs.get("run-1")

    reloaded = run(go())

    assert [s.name for s in reloaded.steps][-1] == "await_approval" and len(reloaded.steps) == 4
    assert reloaded.verify_chain()


def call(run_id, user_id, tin, tout, cost, status="ok") -> LLMCall:
    return LLMCall(
        correlation_id="corr-12345678", user_id=user_id, run_id=run_id, purpose="run",
        provider="ollama", model="m", operation="complete", input_tokens=tin,
        output_tokens=tout, cost_usd=cost, latency_ms=5, status=status, created_at=NOW,
    )


def test_model_calls_are_queryable_by_run_correlation_and_user():
    async def go():
        async with scratch_database() as pool:
            await seed_basics(pool)
            await PostgresRunRepository(pool).save(build_run("run-1", "u-tech"))
            calls = PostgresLLMCallRepository(pool)
            await calls.record(call("run-1", "u-tech", 10, 5, 0.001))
            await calls.record(call("run-1", "u-tech", 20, 5, 0.002, status="error"))
            await calls.record(call(None, "u-sup", 1, 1, 0.0))
            return (
                await calls.calls_for_run("run-1"),
                await calls.calls_for_correlation("corr-12345678"),
                await calls.usage_by_user(datetime(2025, 1, 1, tzinfo=UTC)),
            )

    for_run, for_corr, usage = run(go())

    assert [c.input_tokens for c in for_run] == [10, 20] and len(for_corr) == 3
    by_user = {u.user_id: u for u in usage}
    assert by_user["u-tech"].input_tokens == 30 and by_user["u-tech"].calls == 2
    assert round(by_user["u-tech"].cost_usd, 6) == 0.003


def test_sessions_are_readable_only_by_their_owner():
    async def go():
        async with scratch_database() as pool:
            await seed_basics(pool)
            sessions = PostgresChatSessionRepository(pool)
            mine = await sessions.create_session("u-tech", "How do I reset it?")
            await sessions.add_message(mine.session_id, ChatMessage("user", "q", "asked", NOW))
            await sessions.add_message(
                mine.session_id,
                ChatMessage("assistant", "a", "answered", NOW, citations=[{"chunk_id": "c1"}]),
            )
            return (
                mine,
                await sessions.owns("u-tech", mine.session_id),
                await sessions.owns("u-sup", mine.session_id),
                await sessions.get_session("u-sup", mine.session_id),
                await sessions.get_session("u-tech", mine.session_id),
                await sessions.list_sessions("u-sup"),
            )

    mine, owner_owns, other_owns, other_view, owner_view, other_list = run(go())

    assert owner_owns and not other_owns and other_view is None and other_list == []
    _, messages = owner_view
    assert [m.role for m in messages] == ["user", "assistant"]
    assert messages[1].citations == [{"chunk_id": "c1"}]


def test_document_listings_report_status_and_only_current_documents_are_retrievable():
    async def go():
        async with scratch_database() as pool:
            _, docs = await seed_basics(pool)
            await docs.set_ingestion_status("doc-a", "failed", "embedding service down")
            return (
                await docs.list_with_status(),
                await docs.list_equipment(),
                await docs.list_current_document_ids(),
                await docs.list_current_document_ids("eq-b"),
            )

    rows, equipment, current, current_b = run(go())

    by_id = {r.document.document_id: r for r in rows}
    assert by_id["doc-a"].ingestion_status == "failed"
    assert by_id["doc-a"].ingestion_error == "embedding service down"
    assert by_id["doc-a-old"].ingestion_status == "pending"
    assert [e.equipment_id for e in equipment] == ["eq-a", "eq-b"]
    assert current == ["doc-a"] and current_b == []


def make_work_order(checklist: list[str], status=WorkOrderStatus.PENDING_APPROVAL) -> WorkOrder:
    return WorkOrder(
        work_order_id="wo-1", equipment_id="eq-a", symptom_description="s",
        diagnostic_steps=["check"], safety_checklist=checklist, citations=[],
        created_at=NOW, status=status,
    )


def test_a_work_order_round_trips_and_the_database_refuses_one_without_safety_steps():
    async def go():
        async with scratch_database() as pool:
            await seed_basics(pool)
            repo = PostgresWorkOrderRepository(pool)
            await repo.save(make_work_order(["isolate power"]))
            saved = await repo.get("wo-1")
            try:
                await repo.save(make_work_order([]))
            except asyncpg.CheckViolationError:
                return saved, True
            return saved, False

    saved, refused = run(go())

    assert saved.safety_checklist == ["isolate power"] and saved.status.value == "pending_approval"
    assert refused, "the DB-level CHECK is the second line of defence behind the domain rule"


def test_usernames_are_unique():
    async def go():
        async with scratch_database() as pool:
            users, _ = await seed_basics(pool)
            try:
                await users.create(User("u-other", "tech", Role.ADMIN), "hash")
            except asyncpg.UniqueViolationError:
                return True
            return False

    assert run(go())
