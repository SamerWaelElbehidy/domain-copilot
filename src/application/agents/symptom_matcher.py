from __future__ import annotations

from application.agents.contracts import SymptomMatchResult
from application.agents.names import SYMPTOM_MATCHER
from application.agents.parsing import parse_json_object
from application.agents.tool_loop import LoopResult, run_tool_loop
from application.agents.tool_registry import ToolRegistry
from application.ports.document_repository import DocumentRepository
from application.ports.llm_provider import LLMProvider
from domain.errors.domain_errors import LowEvidenceError
from domain.value_objects.citation import Citation


class SymptomMatcher:
    """Role: turn a free-text symptom into one grounded equipment match.
    Tools: search_manual_chunks, get_document_revisions (read-only).
    Output: SymptomMatchResult. Terminates on a final JSON answer, or on
    the max-iteration breaker. The model only names the equipment; the
    code verifies it against retrieved evidence and resolves the current
    manual revision itself."""

    name = SYMPTOM_MATCHER

    def __init__(
        self,
        *,
        llm: LLMProvider,
        registry: ToolRegistry,
        document_repository: DocumentRepository,
        system_prompt: str,
        max_iterations: int = 4,
    ) -> None:
        self._llm = llm
        self._registry = registry
        self._documents = document_repository
        self._system_prompt = system_prompt
        self._max_iterations = max_iterations

    async def run(self, symptom: str) -> tuple[SymptomMatchResult, LoopResult]:
        loop = await run_tool_loop(
            llm=self._llm,
            registry=self._registry,
            agent_name=self.name,
            system_prompt=self._system_prompt,
            user_message=symptom,
            max_iterations=self._max_iterations,
        )
        equipment_id = parse_json_object(loop.content).get("equipment_id")
        if not isinstance(equipment_id, str) or not equipment_id:
            raise LowEvidenceError("no equipment could be identified from the symptom")

        evidence = [c for c in loop.retrieved_chunks() if c["equipment_id"] == equipment_id]
        if not evidence:
            raise LowEvidenceError(
                f"equipment '{equipment_id}' is not supported by any retrieved evidence"
            )

        documents = [
            d
            for d in await self._documents.list_documents_for_equipment(equipment_id)
            if d.status == "current"
        ]
        manuals = [d for d in documents if d.doc_type == "manual"]
        if not manuals:
            raise LowEvidenceError(f"no current manual exists for '{equipment_id}'")
        current_manual = max(manuals, key=lambda d: d.effective_date)

        seen: set[str] = set()
        citations: list[Citation] = []
        for chunk in evidence:
            if chunk["chunk_id"] not in seen:
                seen.add(chunk["chunk_id"])
                citations.append(
                    Citation(
                        chunk_id=chunk["chunk_id"],
                        document_id=chunk["document_id"],
                        section_title=chunk["section_title"],
                        source_ref=chunk["source_ref"],
                    )
                )

        result = SymptomMatchResult(
            equipment_id=equipment_id,
            document_ids=tuple(d.document_id for d in documents),
            manual_revision=current_manual.revision,
            citations=tuple(citations),
        )
        return result, loop
