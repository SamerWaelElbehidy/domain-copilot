import asyncio
import json

import pytest

from application.agents.contracts import DiagnosticPlan, SymptomMatchResult
from application.agents.diagnostic_planner import DiagnosticSafetyPlanner
from application.agents.names import ORCHESTRATOR, SYMPTOM_MATCHER, WORK_ORDER_GENERATOR
from application.agents.symptom_matcher import SymptomMatcher
from application.agents.work_order_generator import WorkOrderGenerator
from config.prompts import load_prompt
from domain.entities.work_order import WorkOrderStatus
from domain.errors.domain_errors import (
    AgentIterationLimitError,
    AgentOutputError,
    LowEvidenceError,
    MissingSafetyPrerequisiteError,
)
from domain.value_objects.citation import Citation
from tests.fakes.world import build_world, call_tool, say

ROUTER = "eq-cnc-router-dwr2200"
REV_C = "doc-cnc-router-dwr2200-rev-c"
REV_B = "doc-cnc-router-dwr2200-rev-b"
SYMPTOM = "spindle overheating during long runs"


def run(coro):
    return asyncio.run(coro)


def matcher(world):
    return SymptomMatcher(
        llm=world.llm,
        registry=world.registry,
        document_repository=world.documents,
        system_prompt=load_prompt("symptom_matcher").text,
    )


def planner(world):
    return DiagnosticSafetyPlanner(
        llm=world.llm,
        registry=world.registry,
        system_prompt=load_prompt("diagnostic_planner").text,
    )


def generator(world):
    return WorkOrderGenerator(
        llm=world.llm,
        registry=world.registry,
        system_prompt=load_prompt("work_order_generator").text,
    )


def router_match(world) -> SymptomMatchResult:
    docs = run(world.documents.list_documents_for_equipment(ROUTER))
    return SymptomMatchResult(
        equipment_id=ROUTER,
        document_ids=tuple(d.document_id for d in docs if d.status == "current"),
        manual_revision="Rev. C",
        citations=(),
    )


# --- retrieval scoping: superseded revisions are never used -----------------


def test_search_never_returns_superseded_documents():
    world = build_world()

    out = run(
        world.registry.execute(
            SYMPTOM_MATCHER,
            "search_manual_chunks",
            {"query": "dust extraction hose emergency stop", "equipment_id": ROUTER, "top_k": 10},
        )
    )

    document_ids = {c["document_id"] for c in out["chunks"]}
    assert REV_C in document_ids
    assert REV_B not in document_ids


def test_safety_fetch_is_complete_and_current_revision_only():
    world = build_world()
    planner_name = "diagnostic_safety_planner"

    out = run(
        world.registry.execute(planner_name, "get_safety_prerequisites", {"equipment_id": ROUTER})
    )

    contents = [c["content"] for c in out["chunks"]]
    assert {c["document_id"] for c in out["chunks"]} == {REV_C, "doc-cnc-router-dwr2200-loto"}
    assert len(contents) == 7 + 6  # manual Rev. C safety items + LOTO card steps
    assert any("dust extraction hose connection" in c for c in contents)  # added in Rev. C


# --- Symptom Matcher ---------------------------------------------------------


def test_symptom_matcher_resolves_equipment_and_current_revision():
    world = build_world(
        [
            call_tool("search_manual_chunks", {"query": SYMPTOM, "top_k": 5}),
            say(json.dumps({"equipment_id": ROUTER})),
        ]
    )

    result, loop = run(matcher(world).run(SYMPTOM))

    assert result.equipment_id == ROUTER
    assert result.manual_revision == "Rev. C"
    assert REV_B not in result.document_ids and REV_C in result.document_ids
    assert result.citations and all(c.document_id != REV_B for c in result.citations)
    assert [t.tool_name for t in loop.trace] == ["search_manual_chunks"]


def test_symptom_matcher_refuses_an_equipment_id_not_backed_by_retrieved_evidence():
    world = build_world(
        [
            call_tool("search_manual_chunks", {"query": "spindle overheating", "top_k": 5}),
            say(json.dumps({"equipment_id": "eq-air-compressor-iac100"})),
        ]
    )

    with pytest.raises(LowEvidenceError):
        run(matcher(world).run(SYMPTOM))


def test_symptom_matcher_refuses_when_the_model_names_nothing():
    world = build_world([say(json.dumps({"equipment_id": None}))])

    with pytest.raises(LowEvidenceError):
        run(matcher(world).run("the lights in the canteen flicker"))


def test_symptom_matcher_rejects_prose_instead_of_json():
    world = build_world([say("It is probably the router.")])

    with pytest.raises(AgentOutputError):
        run(matcher(world).run(SYMPTOM))


def test_a_tool_outside_the_agents_allow_list_is_refused_and_has_no_effect():
    world = build_world(
        [
            call_tool("dispatch_work_order", {"work_order_id": "wo-1"}),
            say(json.dumps({"equipment_id": None})),
        ]
    )

    with pytest.raises(LowEvidenceError):
        run(matcher(world).run(SYMPTOM))

    assert world.work_orders.work_orders == {}


def test_agent_stops_at_the_iteration_breaker():
    world = build_world([call_tool("search_manual_chunks", {"query": "x"}) for _ in range(10)])

    with pytest.raises(AgentIterationLimitError):
        run(matcher(world).run(SYMPTOM))


# --- Diagnostic & Safety Planner --------------------------------------------


def diagnostic_chunk_id(world) -> str:
    return world.chunk_id(REV_C, "diagnostic", "spindle overheating")


def test_planner_builds_grounded_steps_and_copies_the_full_safety_checklist():
    world = build_world()
    steps = [{"text": "Check the spindle air-cooling intake for dust blockage.",
              "chunk_id": diagnostic_chunk_id(world)}]
    world.llm._responses.append(say(json.dumps({"steps": steps})))

    plan, _ = run(planner(world).run(SYMPTOM, router_match(world)))

    assert plan.diagnostic_steps == ("Check the spindle air-cooling intake for dust blockage.",)
    assert len(plan.safety_checklist) == 13
    assert any("dust extraction hose connection" in s for s in plan.safety_checklist)
    assert all(c.document_id != REV_B for c in plan.citations)


def test_a_model_that_forgets_safety_cannot_shrink_the_checklist():
    """The model's output contains no safety content at all; the checklist
    still comes back complete because code, not the model, produces it."""
    world = build_world()
    steps = [{"text": "Let the spindle cool.", "chunk_id": diagnostic_chunk_id(world)}]
    world.llm._responses.append(say(json.dumps({"steps": steps})))

    plan, _ = run(planner(world).run(SYMPTOM, router_match(world)))

    assert len(plan.safety_checklist) == 13


def test_step_citing_a_chunk_that_was_not_retrieved_is_rejected():
    bad = {"steps": [{"text": "Do a thing.", "chunk_id": "made-up"}]}
    world = build_world([say(json.dumps(bad))])

    with pytest.raises(AgentOutputError):
        run(planner(world).run(SYMPTOM, router_match(world)))


def test_planner_refuses_when_the_model_says_evidence_is_insufficient():
    world = build_world([say(json.dumps({"insufficient": True}))])

    with pytest.raises(LowEvidenceError):
        run(planner(world).run(SYMPTOM, router_match(world)))


def test_planner_refuses_to_plan_when_no_safety_prerequisites_exist():
    world = build_world()
    world.vector_store.chunks = {
        k: c for k, c in world.vector_store.chunks.items()
        if c.section_type.value != "safety_prerequisite"
    }
    world.keyword_index.chunks = {
        k: c for k, c in world.keyword_index.chunks.items()
        if c.section_type.value != "safety_prerequisite"
    }

    with pytest.raises(MissingSafetyPrerequisiteError):
        run(planner(world).run(SYMPTOM, router_match(world)))


def test_planner_refuses_when_there_is_no_diagnostic_evidence():
    world = build_world()
    empty_match = SymptomMatchResult("eq-unknown", (), "Rev. A", ())

    with pytest.raises(LowEvidenceError):
        run(planner(world).run(SYMPTOM, empty_match))


# --- Work Order Generator ----------------------------------------------------


def make_plan(safety=("Lock out power.",)) -> DiagnosticPlan:
    return DiagnosticPlan(
        diagnostic_steps=("Check coolant flow",),
        safety_checklist=tuple(safety),
        citations=(Citation("c1", REV_C, "Diagnostic & Troubleshooting", "ref"),),
    )


def test_generator_drafts_a_work_order_pending_approval_with_the_plans_safety_checklist():
    world = build_world([say(json.dumps({"summary": "Spindle overheats on long runs."}))])
    plan = make_plan(safety=("Lock out power.", "Wear hearing protection."))

    result, _ = run(generator(world).run(SYMPTOM, router_match(world), plan))

    work_order = run(world.work_orders.get(result.work_order_id))
    assert work_order.status == WorkOrderStatus.PENDING_APPROVAL
    assert work_order.safety_checklist == ["Lock out power.", "Wear hearing protection."]
    assert work_order.symptom_description == "Spindle overheats on long runs."


def test_generator_rejects_prose_output_and_creates_nothing():
    world = build_world([say("Sure! Here is your work order.")])

    with pytest.raises(AgentOutputError):
        run(generator(world).run(SYMPTOM, router_match(world), make_plan()))

    assert world.work_orders.work_orders == {}


def test_the_draft_tool_itself_refuses_an_empty_safety_checklist():
    world = build_world()

    with pytest.raises(MissingSafetyPrerequisiteError):
        run(
            world.registry.execute(
                WORK_ORDER_GENERATOR,
                "draft_work_order",
                {
                    "equipment_id": ROUTER,
                    "symptom_description": "x",
                    "diagnostic_steps": ["a"],
                    "safety_checklist": [],
                    "citations": [],
                },
            )
        )

    assert world.work_orders.work_orders == {}


def test_only_the_orchestrator_may_dispatch_and_only_with_approval():
    world = build_world()
    args = {"work_order_id": "wo-1"}

    from domain.errors.domain_errors import ApprovalRequiredError, ToolNotAllowedError

    with pytest.raises(ToolNotAllowedError):
        run(world.registry.execute(WORK_ORDER_GENERATOR, "dispatch_work_order", args))
    with pytest.raises(ApprovalRequiredError):
        run(world.registry.execute(ORCHESTRATOR, "dispatch_work_order", args))
