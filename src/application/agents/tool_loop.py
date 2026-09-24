from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from application.agents.tool_registry import ToolRegistry
from application.ports.llm_provider import LLMProvider, Message
from domain.errors.domain_errors import (
    AgentIterationLimitError,
    InvalidToolArgumentsError,
    ToolNotAllowedError,
)


@dataclass
class ToolTraceEntry:
    tool_name: str
    arguments: Any
    result: Any


@dataclass
class LoopResult:
    content: str
    trace: list[ToolTraceEntry] = field(default_factory=list)
    input_tokens: int = 0
    output_tokens: int = 0
    model: str = ""

    def retrieved_chunks(self) -> list[dict[str, Any]]:
        """Every chunk any tool returned during the loop -- the evidence an
        agent's answer is allowed to be grounded in."""
        chunks: list[dict[str, Any]] = []
        for entry in self.trace:
            if isinstance(entry.result, dict):
                chunks.extend(entry.result.get("chunks", []))
        return chunks


async def run_tool_loop(
    *,
    llm: LLMProvider,
    registry: ToolRegistry,
    agent_name: str,
    system_prompt: str,
    user_message: str,
    tools_enabled: bool = True,
    max_iterations: int = 4,
) -> LoopResult:
    """Bounded tool-calling loop (FR-5 max-iteration breaker). Tool calls go
    through the registry, so allow-list, schema validation and approval
    gating apply no matter what the model asks for. Refused or invalid
    calls are reported back to the model as errors, and count against the
    iteration budget."""
    tools = registry.definitions_for(agent_name) if tools_enabled else []
    messages = [
        Message(role="system", content=system_prompt),
        Message(role="user", content=user_message),
    ]
    result = LoopResult(content="")

    for _ in range(max_iterations):
        completion = await llm.complete(messages, tools or None)
        result.input_tokens += completion.input_tokens
        result.output_tokens += completion.output_tokens
        result.model = completion.model or result.model

        if not completion.tool_calls:
            result.content = completion.content
            return result

        messages.append(
            Message(
                role="assistant",
                content=completion.content,
                tool_calls=tuple(completion.tool_calls),
            )
        )
        for call in completion.tool_calls:
            try:
                outcome: Any = await registry.execute(agent_name, call.name, call.arguments)
            except (ToolNotAllowedError, InvalidToolArgumentsError) as exc:
                outcome = {"error": str(exc)}
            result.trace.append(ToolTraceEntry(call.name, call.arguments, outcome))
            messages.append(
                Message(
                    role="tool",
                    content=json.dumps(outcome, default=str),
                    tool_call_id=call.id or None,
                    name=call.name,
                )
            )

    raise AgentIterationLimitError(
        f"agent '{agent_name}' did not finish within {max_iterations} iterations"
    )
