from __future__ import annotations

from application.agents.contracts import DiagnosticPlan, SymptomMatchResult
from application.agents.names import DIAGNOSTIC_PLANNER
from application.agents.parsing import parse_json_object
from application.agents.tool_loop import LoopResult, run_tool_loop
from application.agents.tool_registry import ToolRegistry
from application.ports.llm_provider import LLMProvider
from domain.errors.domain_errors import (
    AgentOutputError,
    LowEvidenceError,
    MissingSafetyPrerequisiteError,
)
from domain.value_objects.citation import Citation


def _citation(chunk: dict) -> Citation:
    return Citation(
        chunk_id=chunk["chunk_id"],
        document_id=chunk["document_id"],
        section_title=chunk["section_title"],
        source_ref=chunk["source_ref"],
    )


class DiagnosticSafetyPlanner:
    """Role: produce grounded diagnostic steps and the complete safety
    checklist. Tools: search_manual_chunks, get_safety_prerequisites.
    Output: DiagnosticPlan. Terminates after one bounded model call.

    The safety checklist is NOT model output. The code fetches every safety
    prerequisite for the equipment and copies it verbatim, so a model that
    forgets or drops a safety step cannot change the checklist (ADR-0002).
    The model only writes diagnostic steps, each tied to a retrieved chunk."""

    name = DIAGNOSTIC_PLANNER

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
        self, symptom: str, match: SymptomMatchResult
    ) -> tuple[DiagnosticPlan, LoopResult]:
        diagnostics = (
            await self._registry.execute(
                self.name,
                "search_manual_chunks",
                {
                    "query": symptom,
                    "equipment_id": match.equipment_id,
                    "section_type": "diagnostic",
                    "top_k": 5,
                },
            )
        )["chunks"]
        if not diagnostics:
            raise LowEvidenceError("no diagnostic evidence found for this equipment")

        safety = (
            await self._registry.execute(
                self.name, "get_safety_prerequisites", {"equipment_id": match.equipment_id}
            )
        )["chunks"]
        if not safety:
            raise MissingSafetyPrerequisiteError(
                f"no safety prerequisites found for '{match.equipment_id}'; refusing to plan"
            )

        evidence = "\n\n".join(
            f"[chunk_id={c['chunk_id']}] ({c['section_title']})\n{c['content']}"
            for c in diagnostics
        )
        loop = await run_tool_loop(
            llm=self._llm,
            registry=self._registry,
            agent_name=self.name,
            system_prompt=self._system_prompt,
            user_message=f"Symptom: {symptom}\n\nEvidence:\n{evidence}",
            tools_enabled=False,
            max_iterations=self._max_iterations,
        )
        parsed = parse_json_object(loop.content)
        if parsed.get("insufficient") is True:
            raise LowEvidenceError("the model judged the evidence insufficient for this symptom")

        by_id = {c["chunk_id"]: c for c in diagnostics}
        steps = parsed.get("steps")
        if not isinstance(steps, list) or not steps:
            raise LowEvidenceError("the model produced no diagnostic steps")

        step_texts: list[str] = []
        cited: dict[str, Citation] = {}
        for step in steps:
            if not isinstance(step, dict) or not isinstance(step.get("text"), str):
                raise AgentOutputError("each step must be an object with a text field")
            chunk = by_id.get(step.get("chunk_id"))
            if chunk is None:
                raise AgentOutputError(
                    f"step cites unknown chunk_id {step.get('chunk_id')!r}; every step must "
                    "be grounded in retrieved evidence"
                )
            step_texts.append(step["text"].strip())
            cited[chunk["chunk_id"]] = _citation(chunk)
        for chunk in safety:
            cited.setdefault(chunk["chunk_id"], _citation(chunk))

        plan = DiagnosticPlan(
            diagnostic_steps=tuple(step_texts),
            safety_checklist=tuple(c["content"] for c in safety),
            citations=tuple(cited.values()),
        )
        return plan, loop
