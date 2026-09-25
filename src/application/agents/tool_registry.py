from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from application.agents.approval_authority import ApprovalAuthority
from application.ports.llm_provider import ToolDefinition
from domain.errors.domain_errors import (
    ApprovalRequiredError,
    InvalidToolArgumentsError,
    ToolNotAllowedError,
)
from domain.value_objects.approval import ApprovalToken

ToolHandler = Callable[[dict[str, Any]], Awaitable[Any]]

_JSON_TYPES: dict[str, tuple[type, ...]] = {
    "string": (str,),
    "integer": (int,),
    "number": (int, float),
    "boolean": (bool,),
    "array": (list,),
    "object": (dict,),
}


@dataclass(frozen=True)
class ToolSpec:
    definition: ToolDefinition
    handler: ToolHandler
    allowed_agents: frozenset[str]
    side_effecting: bool = False
    requires_approval: bool = False


def validate_arguments(schema: dict[str, Any], arguments: Any) -> None:
    """Minimal JSON-schema check (object with typed properties, required
    keys, no unknown keys) run before any tool executes -- model output is
    untrusted input (OWASP LLM Top 10)."""
    if not isinstance(arguments, dict):
        raise InvalidToolArgumentsError("arguments must be an object")

    properties: dict[str, Any] = schema.get("properties", {})
    for key in schema.get("required", []):
        if key not in arguments:
            raise InvalidToolArgumentsError(f"missing required argument '{key}'")

    for key, value in arguments.items():
        if key not in properties:
            raise InvalidToolArgumentsError(f"unexpected argument '{key}'")
        expected = properties[key].get("type")
        if expected is None:
            continue
        allowed_types = _JSON_TYPES.get(expected)
        if allowed_types is None:
            raise InvalidToolArgumentsError(f"unsupported schema type '{expected}'")
        if isinstance(value, bool) and expected != "boolean":
            raise InvalidToolArgumentsError(f"argument '{key}' must be {expected}")
        if not isinstance(value, allowed_types):
            raise InvalidToolArgumentsError(f"argument '{key}' must be {expected}")
        if "enum" in properties[key] and value not in properties[key]["enum"]:
            raise InvalidToolArgumentsError(f"argument '{key}' not in allowed values")
        if "maximum" in properties[key] and value > properties[key]["maximum"]:
            raise InvalidToolArgumentsError(f"argument '{key}' exceeds maximum")


class ToolRegistry:
    """Single choke point for every tool call: enforces the per-agent
    allow-list, schema validation, and the human-approval requirement
    for gated tools, then executes."""

    def __init__(self, approval_authority: ApprovalAuthority | None = None) -> None:
        self._tools: dict[str, ToolSpec] = {}
        self.approval_authority = approval_authority or ApprovalAuthority()

    def register(self, spec: ToolSpec) -> None:
        name = spec.definition.name
        if name in self._tools:
            raise ValueError(f"tool '{name}' already registered")
        if spec.requires_approval and not spec.side_effecting:
            raise ValueError(f"tool '{name}': only side-effecting tools can require approval")
        if spec.requires_approval and "work_order_id" not in spec.definition.parameters.get(
            "properties", {}
        ):
            raise ValueError(
                f"tool '{name}': a gated tool must take work_order_id "
                "so approval can be bound to it"
            )
        for key, prop in spec.definition.parameters.get("properties", {}).items():
            if prop.get("type") is not None and prop["type"] not in _JSON_TYPES:
                raise ValueError(f"tool '{name}': argument '{key}' has unsupported type")
        self._tools[name] = spec

    def definitions_for(self, agent_name: str) -> list[ToolDefinition]:
        return [
            spec.definition
            for spec in self._tools.values()
            if agent_name in spec.allowed_agents and not spec.requires_approval
        ]

    async def execute(
        self,
        agent_name: str,
        tool_name: str,
        arguments: Any,
        approval: ApprovalToken | None = None,
    ) -> Any:
        """A gated tool runs only with a token issued by this registry's
        ApprovalAuthority for the same work_order_id as the call's arguments."""
        spec = self._tools.get(tool_name)
        if spec is None or agent_name not in spec.allowed_agents:
            raise ToolNotAllowedError(f"agent '{agent_name}' may not call tool '{tool_name}'")
        validate_arguments(spec.definition.parameters, arguments)
        if spec.requires_approval and not self.approval_authority.verify(
            approval, arguments.get("work_order_id")
        ):
            raise ApprovalRequiredError(
                f"tool '{tool_name}' requires a valid human approval for this work order"
            )
        return await spec.handler(arguments)
