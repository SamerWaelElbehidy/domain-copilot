from __future__ import annotations

import re
from dataclasses import dataclass

from application.agents.parsing import parse_json_object
from application.ports.document_repository import DocumentRepository
from application.ports.keyword_search_index import KeywordSearchIndex
from application.ports.llm_provider import LLMProvider, Message
from application.ports.vector_store import VectorStore
from application.use_cases.conflict_check import find_conflict
from application.use_cases.grounding import support_score
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
    detail: str | None = None  # e.g. which sources disagree
    input_tokens: int = 0
    output_tokens: int = 0
    model: str = ""

    def as_dict(self) -> dict:
        return {
            "status": self.status,
            "answer": self.text,
            "reason": self.reason,
            "detail": self.detail,
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


def _refuse(
    reason: str, chunks: list[Chunk], top: float, detail: str | None = None, **usage
) -> Answer:
    return Answer(
        "refused", "", (), reason, tuple(c.chunk_id for c in chunks), top, tuple(chunks),
        detail, **usage,
    )


class GroundedAnswerer:
    """Plain RAG with verifiable citations (FR-2), and also the graceful
    degradation target for the orchestrator (FR-5).

    Grounding is enforced in code, not trusted to the model: no evidence or
    a dense score below `min_dense_score` refuses before any model call,
    and an answer is accepted only if every excerpt number it cites exists
    (excerpts are numbered in the prompt and mapped back to chunk ids here)
    and the answer's own words must be supported by the excerpts it cites, so
    a bare "1" or an invented value is refused rather than shown. If another
    retrieved document states a different value for the same measurement, the
    answer is withheld and the disagreement is reported instead.
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
        min_support: float = 0.5,
        filter_suspicious: bool = True,
    ) -> None:
        self._llm = llm
        self._vector_store = vector_store
        self._keyword_index = keyword_index
        self._documents = document_repository
        self._system_prompt = system_prompt
        self._top_k = top_k
        self._min_dense_score = min_dense_score
        self._min_support = min_support
        self._filter_suspicious = filter_suspicious

    async def answer(self, question: str, equipment_id: str | None = None) -> Answer:
        found = await scoped_search(
            llm_provider=self._llm,
            vector_store=self._vector_store,
            keyword_index=self._keyword_index,
            document_repository=self._documents,
            query=question,
            equipment_id=equipment_id,
            top_k=self._top_k,
            filter_suspicious=self._filter_suspicious,
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
        cited_texts = [chunks[n - 1].content for n in numbers]
        if support_score(text, cited_texts) < self._min_support:
            return _refuse("unsupported_answer", chunks, top, **usage)

        cited_chunks = [chunks[n - 1] for n in numbers]
        conflict = find_conflict(
            answer_text=text,
            cited=cited_chunks,
            others=[c for c in chunks if c not in cited_chunks],
        )
        if conflict is not None:
            return _refuse(
                "conflicting_sources", chunks, top, detail=conflict.describe(), **usage
            )

        return Answer(
            "answered", text.strip(), citations, None,
            tuple(c.chunk_id for c in chunks), top, tuple(chunks), **usage,
        )
