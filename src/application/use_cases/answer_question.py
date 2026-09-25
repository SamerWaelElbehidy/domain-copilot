from __future__ import annotations

import re
from dataclasses import dataclass

from application.agents.parsing import parse_json_object
from application.ports.document_repository import DocumentRepository
from application.ports.keyword_search_index import KeywordSearchIndex
from application.ports.llm_provider import LLMProvider, Message
from application.ports.vector_store import VectorStore
from application.use_cases.scoped_search import scoped_search
from domain.entities.chunk import Chunk
from domain.errors.domain_errors import AgentOutputError
from domain.value_objects.citation import Citation

_TAG = re.compile(r"</?\s*document[^>]*>", re.IGNORECASE)


@dataclass(frozen=True)
class Answer:
    status: str  # "answered" | "refused"
    text: str
    citations: tuple[Citation, ...]
    reason: str | None
    retrieved_chunk_ids: tuple[str, ...]
    top_dense_score: float
    evidence: tuple[Chunk, ...] = ()
    input_tokens: int = 0
    output_tokens: int = 0
    model: str = ""

    def as_dict(self) -> dict:
        return {
            "status": self.status,
            "answer": self.text,
            "reason": self.reason,
            "citations": [c.__dict__ for c in self.citations],
        }


def _sanitize(text: str) -> str:
    """Retrieved text must not be able to close or forge the <document>
    wrapper that separates data from instructions."""
    return _TAG.sub("", text)


def _as_excerpt_numbers(raw: object, available: int) -> list[int]:
    """Excerpts are numbered 1..N in the prompt and the model cites those
    numbers; code maps them back to chunk ids. Anything that is not a valid
    excerpt number (including an empty list) yields [] and the answer is
    treated as ungrounded."""
    if not isinstance(raw, list) or not raw:
        return []
    numbers: list[int] = []
    for item in raw:
        if isinstance(item, bool):
            return []
        if isinstance(item, str) and item.strip().isdigit():
            item = int(item.strip())
        if not isinstance(item, int) or not 1 <= item <= available:
            return []
        if item not in numbers:
            numbers.append(item)
    return numbers


def _refuse(reason: str, chunks: list[Chunk], top: float, **usage) -> Answer:
    return Answer(
        "refused", "", (), reason, tuple(c.chunk_id for c in chunks), top, tuple(chunks), **usage
    )


class GroundedAnswerer:
    """Plain RAG with verifiable citations (FR-2), and also the graceful
    degradation target for the orchestrator (FR-5).

    Grounding is enforced in code, not trusted to the model: no evidence or
    a dense score below `min_dense_score` refuses before any model call,
    and an answer is accepted only if every excerpt number it cites exists
    (excerpts are numbered in the prompt and mapped back to chunk ids here).
    "Not enough information" is a correct and required answer."""

    def __init__(
        self,
        *,
        llm: LLMProvider,
        vector_store: VectorStore,
        keyword_index: KeywordSearchIndex,
        document_repository: DocumentRepository,
        system_prompt: str,
        top_k: int = 5,
        min_dense_score: float = 0.0,
    ) -> None:
        self._llm = llm
        self._vector_store = vector_store
        self._keyword_index = keyword_index
        self._documents = document_repository
        self._system_prompt = system_prompt
        self._top_k = top_k
        self._min_dense_score = min_dense_score

    async def answer(self, question: str, equipment_id: str | None = None) -> Answer:
        found = await scoped_search(
            llm_provider=self._llm,
            vector_store=self._vector_store,
            keyword_index=self._keyword_index,
            document_repository=self._documents,
            query=question,
            equipment_id=equipment_id,
            top_k=self._top_k,
        )
        chunks, top = found.chunks, found.top_dense_score
        if not chunks:
            return _refuse("no_evidence", chunks, top)
        if top < self._min_dense_score:
            return _refuse("below_relevance_threshold", chunks, top)

        evidence = "\n\n".join(
            f'<document id="{n}">\n{_sanitize(c.content)}\n</document>'
            for n, c in enumerate(chunks, start=1)
        )
        completion = await self._llm.complete(
            [
                Message(role="system", content=self._system_prompt),
                Message(role="user", content=f"Question: {question}\n\nExcerpts:\n{evidence}"),
            ],
            json_mode=True,
        )
        usage = {
            "input_tokens": completion.input_tokens,
            "output_tokens": completion.output_tokens,
            "model": completion.model,
        }
        try:
            parsed = parse_json_object(completion.content)
        except AgentOutputError:
            return _refuse("invalid_model_output", chunks, top, **usage)

        if parsed.get("insufficient") is True:
            return _refuse("model_judged_insufficient", chunks, top, **usage)

        text = parsed.get("answer")
        numbers = _as_excerpt_numbers(parsed.get("citations"), len(chunks))
        if not isinstance(text, str) or not text.strip() or not numbers:
            return _refuse("ungrounded_answer", chunks, top, **usage)

        citations = tuple(
            Citation(
                chunk_id=chunks[n - 1].chunk_id,
                document_id=chunks[n - 1].document_id,
                section_title=chunks[n - 1].section_title,
                source_ref=chunks[n - 1].source_ref,
            )
            for n in numbers
        )
        return Answer(
            "answered", text.strip(), citations, None,
            tuple(c.chunk_id for c in chunks), top, tuple(chunks), **usage,
        )
