from __future__ import annotations

import dataclasses

from application.agents.contracts import DiagnosticPlan, SymptomMatchResult, WorkOrderDraftResult
from application.agents.names import WORK_ORDER_GENERATOR
from application.agents.parsing import parse_json_object
from application.agents.tool_loop import LoopResult, run_tool_loop
from application.agents.tool_registry import ToolRegistry
from application.ports.llm_provider import LLMProvider
from domain.errors.domain_errors import AgentOutputError

MAX_SUMMARY_CHARS = 500


class WorkOrderGenerator:
    """Role: draft the work order. Tools: draft_work_order (write, creates
    a draft and submits it for approval; never dispatches).
    Output: WorkOrderDraftResult. The model writes only the header summary;
    steps, safety checklist and citations come from the verified plan and
    are passed to the tool by code, never through model-controlled arguments."""

    name = WORK_ORDER_GENERATOR

    def __init__(
        self,
        *,
        llm: LLMProvider,
        registry: ToolRegistry,
        system_prompt: str,
        max_iterations: int = 2,
    ) -> None:
        self._llm = llm
        self._registry = registry
        self._system_prompt = system_prompt
        self._max_iterations = max_iterations

    async def run(
        self, symptom: str, match: SymptomMatchResult, plan: DiagnosticPlan
    ) -> tuple[WorkOrderDraftResult, LoopResult]:
        steps = "\n".join(f"{i}. {s}" for i, s in enumerate(plan.diagnostic_steps, 1))
        loop = await run_tool_loop(
            llm=self._llm,
            registry=self._registry,
            agent_name=self.name,
            system_prompt=self._system_prompt,
            user_message=f"Symptom: {symptom}\n\nVerified diagnostic steps:\n{steps}",
            tools_enabled=False,
            max_iterations=self._max_iterations,
        )
        summary = parse_json_object(loop.content).get("summary")
        if not isinstance(summary, str) or not summary.strip():
            raise AgentOutputError("work order summary missing from model output")

        outcome = await self._registry.execute(
            self.name,
            "draft_work_order",
            {
                "equipment_id": match.equipment_id,
                "symptom_description": summary.strip()[:MAX_SUMMARY_CHARS],
                "diagnostic_steps": list(plan.diagnostic_steps),
                "safety_checklist": list(plan.safety_checklist),
                "citations": [dataclasses.asdict(c) for c in plan.citations],
            },
        )
        return WorkOrderDraftResult(work_order_id=outcome["work_order_id"]), loop
