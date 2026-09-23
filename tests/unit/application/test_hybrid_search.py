import asyncio

from application.ports.vector_store import ScoredChunk
from application.use_cases.hybrid_search import hybrid_search
from domain.entities.chunk import Chunk
from domain.value_objects.section_type import SectionType
from tests.fakes.fake_keyword_search_index import FakeKeywordSearchIndex
from tests.fakes.fake_vector_store import FakeVectorStore


def make_chunk(chunk_id: str) -> Chunk:
    return Chunk(
        chunk_id=chunk_id,
        document_id="doc-1",
        equipment_id="eq-1",
        manual_revision="Rev. A",
        section_type=SectionType.OVERVIEW,
        section_title="Overview & Specifications",
        content=f"content for {chunk_id}",
        order_index=0,
        source_ref="ref",
    )


def test_chunk_ranked_high_in_both_rankers_wins_fusion():
    chunk_a, chunk_b, chunk_c = make_chunk("a"), make_chunk("b"), make_chunk("c")

    vector_store = FakeVectorStore(
        [ScoredChunk(chunk=chunk_a, score=0.9), ScoredChunk(chunk=chunk_b, score=0.5)]
    )
    keyword_index = FakeKeywordSearchIndex(
        [ScoredChunk(chunk=chunk_a, score=0.8), ScoredChunk(chunk=chunk_c, score=0.3)]
    )

    results = asyncio.run(
        hybrid_search(
            vector_store=vector_store,
            keyword_index=keyword_index,
            query_embedding=[0.1, 0.2],
            query_text="overview",
            top_k=3,
        )
    )

    assert results[0].chunk_id == "a"
    assert {c.chunk_id for c in results} == {"a", "b", "c"}


def test_top_k_limits_the_fused_result_count():
    chunks = [make_chunk(f"c{i}") for i in range(5)]
    vector_store = FakeVectorStore([ScoredChunk(chunk=c, score=1.0) for c in chunks])
    keyword_index = FakeKeywordSearchIndex([])

    results = asyncio.run(
        hybrid_search(
            vector_store=vector_store,
            keyword_index=keyword_index,
            query_embedding=[0.1],
            query_text="x",
            top_k=2,
        )
    )

    assert len(results) == 2


def test_chunk_present_in_only_one_ranker_still_appears():
    chunk_a = make_chunk("a")

    vector_store = FakeVectorStore([ScoredChunk(chunk=chunk_a, score=0.9)])
    keyword_index = FakeKeywordSearchIndex([])

    results = asyncio.run(
        hybrid_search(
            vector_store=vector_store,
            keyword_index=keyword_index,
            query_embedding=[0.1],
            query_text="x",
            top_k=5,
        )
    )

    assert [c.chunk_id for c in results] == ["a"]
