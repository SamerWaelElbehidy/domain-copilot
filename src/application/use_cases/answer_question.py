from __future__ import annotations

import re
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any

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

    async def _retrieve(
        self, question: str, equipment_id: str | None
    ) -> tuple[list[Chunk], float, int, Answer | None]:
        """Retrieval and the gates that need no model. Returns a ready refusal
        when the question can be turned away before any generation."""
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
            return chunks, top, found.quarantined, _refuse("no_evidence", chunks, top)
        if top < self._min_dense_score:
            refusal = _refuse("below_relevance_threshold", chunks, top)
            return chunks, top, found.quarantined, refusal
        return chunks, top, found.quarantined, None

    def _messages(self, question: str, chunks: list[Chunk]) -> list[Message]:
        evidence = "\n\n".join(
            f'<document id="{n}">\n{_sanitize(c.content)}\n</document>'
            for n, c in enumerate(chunks, start=1)
        )
        return [
            Message(role="system", content=self._system_prompt),
            Message(role="user", content=f"Question: {question}\n\nExcerpts:\n{evidence}"),
        ]

    def _validate(self, content: str, chunks: list[Chunk], top: float, usage: dict) -> Answer:
        """Every guard that decides whether model output may be shown. Shared
        by the JSON and the streaming path so they can never diverge."""
        try:
            parsed = parse_json_object(content)
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
        cited_chunks = [chunks[n - 1] for n in numbers]
        if support_score(text, [c.content for c in cited_chunks]) < self._min_support:
            return _refuse("unsupported_answer", chunks, top, **usage)

        conflict = find_conflict(
            answer_text=text,
            cited=cited_chunks,
            others=[c for c in chunks if c not in cited_chunks],
        )
        if conflict is not None:
            return _refuse("conflicting_sources", chunks, top, detail=conflict.describe(), **usage)

        return Answer(
            "answered", text.strip(), citations, None,
            tuple(c.chunk_id for c in chunks), top, tuple(chunks), **usage,
        )

    async def answer(self, question: str, equipment_id: str | None = None) -> Answer:
        chunks, top, _, refusal = await self._retrieve(question, equipment_id)
        if refusal is not None:
            return refusal
        completion = await self._llm.complete(self._messages(question, chunks), json_mode=True)
        usage = {
            "input_tokens": completion.input_tokens,
            "output_tokens": completion.output_tokens,
            "model": completion.model,
        }
        return self._validate(completion.content, chunks, top, usage)

    async def answer_stream(
        self, question: str, equipment_id: str | None = None
    ) -> AsyncIterator[dict[str, Any]]:
        """Same pipeline, streamed (FR-6). Events: `retrieval` (which excerpts
        were found), `token` (raw model output as it is produced), and a final
        `answer` carrying the validated result. The streamed tokens are
        provisional: nothing is shown as the answer until every guard has run.
        Closing this iterator closes the provider stream, which stops the model."""
        chunks, top, quarantined, refusal = await self._retrieve(question, equipment_id)
        yield {
            "type": "retrieval",
            "excerpts": [
                {"n": i, "document_id": c.document_id, "section": c.section_title,
                 "source": c.source_ref}
                for i, c in enumerate(chunks, start=1)
            ],
            "quarantined": quarantined,
            "top_dense_score": round(top, 3),
        }
        if refusal is not None:
            yield {"type": "answer", "answer": refusal.as_dict()}
            return

        content, usage = "", {"input_tokens": 0, "output_tokens": 0, "model": ""}
        stream = self._llm.stream(self._messages(question, chunks), json_mode=True)
        try:
            async for event in stream:
                if event.kind == "token":
                    content += event.text
                    yield {"type": "token", "text": event.text}
                elif event.kind == "done":
                    usage = {
                        "input_tokens": event.input_tokens,
                        "output_tokens": event.output_tokens,
                        "model": event.model,
                    }
        finally:
            await stream.aclose()
        yield {"type": "answer", "answer": self._validate(content, chunks, top, usage).as_dict()}
