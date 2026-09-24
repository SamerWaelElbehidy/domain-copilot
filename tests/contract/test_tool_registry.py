import asyncio
from datetime import datetime

import pytest

from application.agents.tool_registry import ToolRegistry, ToolSpec, validate_arguments
from application.ports.llm_provider import ToolDefinition
from domain.errors.domain_errors import (
    ApprovalRequiredError,
    InvalidToolArgumentsError,
    ToolNotAllowedError,
)
from domain.value_objects.approval import ApprovalToken

SEARCH_SCHEMA = {
    "type": "object",
    "properties": {
        "query": {"type": "string"},
        "top_k": {"type": "integer", "maximum": 10},
        "section_type": {"type": "string", "enum": ["safety_prerequisite", "diagnostic"]},
    },
    "required": ["query"],
}


def make_registry(calls: list) -> ToolRegistry:
    async def search(args):
        calls.append(("search", args))
        return {"chunks": []}

    async def dispatch(args):
        calls.append(("dispatch", args))
        return {"dispatched": True}

    registry = ToolRegistry()
    registry.register(
        ToolSpec(
            definition=ToolDefinition("search_manual_chunks", "search", SEARCH_SCHEMA),
            handler=search,
            allowed_agents=frozenset({"symptom_matcher", "diagnostic_planner"}),
        )
    )
    registry.register(
        ToolSpec(
            definition=ToolDefinition(
                "dispatch_work_order",
                "dispatch",
                {"type": "object", "properties": {"work_order_id": {"type": "string"}},
                 "required": ["work_order_id"]},
            ),
            handler=dispatch,
            allowed_agents=frozenset({"orchestrator"}),
            side_effecting=True,
            requires_approval=True,
        )
    )
    return registry


def run(coro):
    return asyncio.run(coro)


def test_allowed_agent_executes_a_valid_call():
    calls: list = []
    registry = make_registry(calls)

    result = run(registry.execute("symptom_matcher", "search_manual_chunks", {"query": "x"}))

    assert result == {"chunks": []}
    assert calls == [("search", {"query": "x"})]


def test_agent_outside_the_allow_list_is_refused_and_handler_never_runs():
    calls: list = []
    registry = make_registry(calls)

    with pytest.raises(ToolNotAllowedError):
        run(registry.execute("work_order_generator", "search_manual_chunks", {"query": "x"}))

    assert calls == []


def test_unknown_tool_is_refused():
    with pytest.raises(ToolNotAllowedError):
        run(make_registry([]).execute("symptom_matcher", "rm_rf", {}))


def test_gated_tool_without_approval_is_refused_even_for_its_allowed_agent():
    calls: list = []
    registry = make_registry(calls)

    with pytest.raises(ApprovalRequiredError):
        run(registry.execute("orchestrator", "dispatch_work_order", {"work_order_id": "wo-1"}))

    assert calls == []


def test_gated_tool_with_approval_token_executes():
    calls: list = []
    registry = make_registry(calls)
    token = ApprovalToken("wo-1", "supervisor-1", datetime(2026, 1, 2))

    result = run(
        registry.execute(
            "orchestrator", "dispatch_work_order", {"work_order_id": "wo-1"}, approval=token
        )
    )

    assert result == {"dispatched": True}


def test_agents_are_never_shown_gated_tools():
    registry = make_registry([])

    assert [d.name for d in registry.definitions_for("orchestrator")] == []
    assert [d.name for d in registry.definitions_for("symptom_matcher")] == ["search_manual_chunks"]


@pytest.mark.parametrize(
    "arguments",
    [
        {},  # missing required
        {"query": 5},  # wrong type
        {"query": "x", "top_k": 99},  # over maximum (unbounded consumption)
        {"query": "x", "section_type": "parts"},  # not in enum
        {"query": "x", "extra": 1},  # unexpected key
        {"query": "x", "top_k": True},  # bool is not an integer
        "not-an-object",
    ],
)
def test_invalid_arguments_are_rejected_before_execution(arguments):
    with pytest.raises(InvalidToolArgumentsError):
        validate_arguments(SEARCH_SCHEMA, arguments)


def test_only_side_effecting_tools_may_require_approval():
    registry = ToolRegistry()

    async def handler(args):
        return None

    with pytest.raises(ValueError):
        registry.register(
            ToolSpec(
                definition=ToolDefinition("t", "d", {"type": "object", "properties": {}}),
                handler=handler,
                allowed_agents=frozenset({"a"}),
                side_effecting=False,
                requires_approval=True,
            )
        )
