import asyncio
import json
from pathlib import Path

from application.use_cases.answer_question import GroundedAnswerer
from application.use_cases.conflict_check import find_conflict, measurements
from application.use_cases.ingest_and_index_document import ingest_and_index_markdown_document
from application.use_cases.scoped_search import scoped_search
from config.prompts import load_prompt
from domain.entities.chunk import Chunk
from domain.value_objects.section_type import SectionType
from infrastructure.corpus.loader import load_corpus
from tests.fakes.world import build_world, say

ROOT = Path(__file__).resolve().parents[3]
EXTRA = ROOT / "eval" / "extra_corpus"


def chunk(document_id: str, content: str, n: int = 0) -> Chunk:
    return Chunk(f"{document_id}::{n}", document_id, "eq", "Rev. A", SectionType.OPERATING,
                 "Operating Procedures", content, n, "ref")


def run(coro):
    return asyncio.run(coro)


# --- measurement extraction ---------------------------------------------------


def test_numbers_with_units_are_extracted_and_units_normalised():
    found = {(m.value, m.unit) for m in measurements(
        "Wait 30 minutes; runout above 0.05mm; face velocity 0.5 m/s; below 40C; 2 hours"
    )}

    assert found == {(30.0, "min"), (0.05, "mm"), (0.5, "m/s"), (40.0, "c"), (2.0, "h")}


def test_list_numbers_and_bare_digits_are_not_measurements():
    assert measurements("1. Confirm the belt guard. 2. Wear hearing protection.") == []


# --- conflict detection ---------------------------------------------------------


def test_a_differing_value_for_the_same_parameter_in_another_document_is_a_conflict():
    manual = chunk("manual", "Minimum booth face velocity before spraying: 0.5 m/s on the gauge.")
    memo = chunk("memo", "Minimum booth face velocity before spraying: 0.3 m/s on the gauge.")

    conflict = find_conflict(
        answer_text="The minimum face velocity is 0.5 m/s.", cited=[manual], others=[memo]
    )

    assert conflict is not None
    assert conflict.answered_document == "manual" and conflict.other_document == "memo"
    assert "0.5 m/s" in conflict.describe() and "0.3 m/s" in conflict.describe()


def test_the_same_value_in_two_documents_is_not_a_conflict():
    a = chunk("a", "Minimum booth face velocity before spraying: 0.5 m/s on the gauge.")
    b = chunk("b", "Minimum booth face velocity before spraying: 0.5 m/s on the gauge.")

    assert find_conflict(answer_text="0.5 m/s", cited=[a], others=[b]) is None


def test_the_same_unit_about_a_different_parameter_is_not_a_conflict():
    isolation = chunk("loto", "Wait 30 seconds after electrical isolation before touching housing.")
    startup = chunk("manual", "Start the dust extraction 10 seconds before starting the spindle.")

    assert find_conflict(
        answer_text="Wait 30 seconds after isolation.", cited=[isolation], others=[startup]
    ) is None


def test_values_within_one_document_are_never_compared():
    one = chunk("doc", "Minimum booth face velocity before spraying: 0.5 m/s on the gauge.", 0)
    two = chunk("doc", "Minimum booth face velocity before spraying: 0.3 m/s on the gauge.", 1)

    assert find_conflict(answer_text="0.5 m/s", cited=[one], others=[two]) is None


def test_an_answer_with_no_measurement_is_not_checked():
    a = chunk("a", "Minimum booth face velocity before spraying: 0.5 m/s on the gauge.")
    b = chunk("b", "Minimum booth face velocity before spraying: 0.3 m/s on the gauge.")

    assert find_conflict(answer_text="Check the gauge first.", cited=[a], others=[b]) is None


# --- no false positives on the real corpus ---------------------------------------


def test_no_chunk_of_the_real_corpus_conflicts_with_another_real_document():
    """Treats every chunk as if it were the cited answer and compares it with every
    chunk of every other current document. A hit here would refuse a correct
    answer, so any genuine cross-document disagreement must be found and fixed
    in the corpus rather than tolerated."""
    from application.use_cases.ingest_document import ingest_markdown_document

    items = [i for i in load_corpus(ROOT / "corpus") if i.document.status == "current"]
    chunks = [c for item in items for c in ingest_markdown_document(item.raw_text)]

    flagged = []
    for c in chunks:
        conflict = find_conflict(
            answer_text=c.content, cited=[c], others=[o for o in chunks if o is not c]
        )
        if conflict:
            flagged.append(conflict.describe())

    assert flagged == [], " | ".join(flagged)


def test_values_for_different_machines_are_never_compared():
    glue = Chunk("g", "d1", "eq-edge-bander", "Rev. A", SectionType.OPERATING, "t",
                 "Wear heat resistant gloves below 60C during contact cleaning.", 0, "r")
    press = Chunk("p", "d2", "eq-press", "Rev. A", SectionType.OPERATING, "t",
                  "Wear heat resistant gloves below 40C during contact cleaning.", 0, "r")

    assert find_conflict(answer_text="below 60C", cited=[glue], others=[press]) is None


def test_a_facility_wide_policy_is_compared_with_any_manual():
    manual = Chunk("m", "d1", "eq-router", "Rev. A", SectionType.OPERATING, "t",
                   "Hot work needs a permit within 10 meters of the ducting.", 0, "r")
    policy = Chunk("f", "d2", "eq-facility-general", "Rev. A", SectionType.OPERATING, "t",
                   "Hot work needs a permit within 5 meters of the ducting.", 0, "r")

    assert find_conflict(answer_text="within 10 meters", cited=[manual], others=[policy])


# --- end to end through the answerer ------------------------------------------------


def world_with_memo():
    world = build_world()
    memo = (EXTRA / "memo-booth-face-velocity.md").read_text(encoding="utf-8")
    run(ingest_and_index_markdown_document(
        raw_text=memo, llm_provider=world.llm,
        vector_store=world.vector_store, keyword_index=world.keyword_index,
    ))
    run(world.documents.save_document(
        next(i.document for i in load_corpus(EXTRA) if "memo-fv" in i.document.document_id)
    ))
    return world


QUESTION = "What is the minimum booth face velocity for the SFB-300 before spraying starts?"


def make_answerer(world):
    return GroundedAnswerer(
        llm=world.llm, vector_store=world.vector_store, keyword_index=world.keyword_index,
        document_repository=world.documents,
        system_prompt=load_prompt("answer_question", "v3").text, top_k=5,
    )


def test_the_answerer_withholds_an_answer_when_sources_disagree_and_reports_both():
    world = world_with_memo()
    found = run(scoped_search(
        llm_provider=world.llm, vector_store=world.vector_store,
        keyword_index=world.keyword_index, document_repository=world.documents,
        query=QUESTION, top_k=5,
    ))
    position = next(
        i for i, c in enumerate(found.chunks, 1)
        if "0.5 m/s" in c.content and c.document_id == "doc-spray-booth-sfb300-rev-a"
    )
    world.llm._responses.append(
        say(json.dumps({"answer": "The minimum face velocity is 0.5 m/s.",
                        "citations": [position]}))
    )

    result = run(make_answerer(world).answer(QUESTION))

    assert result.status == "refused" and result.reason == "conflicting_sources"
    assert "0.5 m/s" in result.detail and "0.3 m/s" in result.detail
    assert "doc-spray-booth-sfb300-memo-fv-conflict" in result.detail


def test_the_same_answer_is_given_when_no_conflicting_document_exists():
    world = build_world()
    found = run(scoped_search(
        llm_provider=world.llm, vector_store=world.vector_store,
        keyword_index=world.keyword_index, document_repository=world.documents,
        query=QUESTION, top_k=5,
    ))
    position = next(i for i, c in enumerate(found.chunks, 1) if "0.5 m/s" in c.content)
    world.llm._responses.append(
        say(json.dumps({"answer": "The minimum face velocity is 0.5 m/s.",
                        "citations": [position]}))
    )

    result = run(make_answerer(world).answer(QUESTION))

    assert result.status == "answered"


def test_the_router_collet_runout_memo_conflicts_with_the_manual():
    from application.use_cases.ingest_document import ingest_markdown_document

    manual = ingest_markdown_document(
        (ROOT / "corpus" / "cnc-wood-router-dwr2200" / "manual-rev-c.md").read_text("utf-8")
    )
    memo = ingest_markdown_document(
        (EXTRA / "memo-router-collet-runout.md").read_text("utf-8")
    )
    cited = next(c for c in manual if "0.05mm" in c.content)

    conflict = find_conflict(
        answer_text="Replace the collet if runout exceeds 0.05mm.", cited=[cited], others=memo
    )

    assert conflict is not None and "0.15mm" in conflict.describe()
