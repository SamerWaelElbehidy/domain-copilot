import pytest

from api.container import IngestionDeps
from domain.value_objects.role import Role
from infrastructure.documents.pypdf_extractor import PypdfTextExtractor
from tests.api.test_auth_and_security import Stack, make_settings
from tests.fakes.fake_llm_provider import FakeLLMProvider
from tests.fakes.in_memory import (
    InMemoryDocumentRepository,
    InMemoryKeywordIndex,
    InMemoryVectorStore,
)
from tests.fakes.pdf_builder import manual_pdf

MARKDOWN = """---
equipment_id: eq-test-press-tp100
equipment_name: Test Press TP-100
document_id: doc-test-press-tp100-rev-a
revision: Rev. A
effective_date: 2026-01-15
---

# Test Press TP-100 - Maintenance Manual

## Safety Prerequisites

1. Isolate power and apply lockout before opening the guard.

## Diagnostic & Troubleshooting

1. Symptom: hydraulic pressure low. Likely cause: low reservoir level or a
   blocked pump inlet filter. Corrective action: check the reservoir level
   and inspect the pump inlet filter before resuming.
"""


class DocStack(Stack):
    def __init__(self, upload_max_bytes: int = 200_000) -> None:
        super().__init__(make_settings(max_body_bytes=200_000, upload_max_bytes=upload_max_bytes))
        self.llm = FakeLLMProvider(embedding_dim=64)
        self.vectors = InMemoryVectorStore()
        self.keywords = InMemoryKeywordIndex()
        self.documents = InMemoryDocumentRepository()
        self.container.documents = self.documents
        self.container.ingestion = IngestionDeps(
            pdf_extractor=PypdfTextExtractor(),
            llm_provider=self.llm,
            vector_store=self.vectors,
            keyword_index=self.keywords,
            document_repository=self.documents,
        )
        self.add_user("tech1", Role.TECHNICIAN)
        self.add_user("super1", Role.SUPERVISOR)
        self.add_user("admin1", Role.ADMIN)

    def upload(self, who="admin1", name="press.md", content=MARKDOWN.encode(), **fields):
        return self.client.post(
            "/documents",
            files={"file": (name, content)},
            data=fields,
            headers=self.auth(who),
        )


@pytest.fixture
def stack():
    return DocStack()


def test_only_an_admin_may_upload_or_list(stack):
    for who in ("tech1", "super1"):
        assert stack.upload(who).status_code == 403
        assert stack.client.get("/documents", headers=stack.auth(who)).status_code == 403
    assert stack.client.post("/documents", files={"file": ("a.md", b"x")}).status_code == 401


def test_a_markdown_upload_is_ingested_indexed_and_listed(stack):
    response = stack.upload()

    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "ingested" and body["chunks"] >= 2
    assert body["uploaded_by"] == "admin1"
    assert stack.vectors.chunks and stack.keywords.chunks
    (row,) = stack.client.get("/documents", headers=stack.auth("admin1")).json()
    assert row["document_id"] == "doc-test-press-tp100-rev-a"
    assert row["ingestion_status"] == "ingested" and row["status"] == "current"
    assert stack.documents.equipment["eq-test-press-tp100"].model_number == "TP-100"


def test_a_pdf_upload_takes_its_metadata_from_form_fields(stack):
    pdf = manual_pdf(MARKDOWN.split("---\n", 2)[2])

    response = stack.upload(
        name="press.pdf",
        content=pdf,
        equipment_id="eq-test-press-tp100",
        equipment_name="Test Press TP-100",
        document_id="doc-test-press-tp100-rev-a-pdf",
        revision="Rev. A",
        effective_date="2026-01-15",
        doc_type="manual",
    )

    assert response.status_code == 201 and response.json()["chunks"] >= 2


def test_reuploading_the_same_document_replaces_its_chunks(stack):
    first = stack.upload().json()["chunks"]
    stack.upload()

    assert len(stack.vectors.chunks) == first


@pytest.mark.parametrize(
    "name,content",
    [
        ("notes.txt", b"plain text"),
        ("evil.md", b"---\x00\x01binary"),
        ("fake.pdf", b"not a pdf at all"),
        ("archive.zip", b"PK\x03\x04"),
    ],
)
def test_unsupported_or_disguised_files_are_rejected_before_anything_is_stored(
    stack, name, content
):
    response = stack.upload(name=name, content=content)

    assert response.status_code == 422
    assert stack.documents.documents == {} and stack.vectors.chunks == {}


def test_missing_or_malformed_metadata_is_rejected(stack):
    no_meta = stack.upload(content=b"# Title\n\n## Safety Prerequisites\n\n1. Isolate power.\n")
    bad_id = stack.upload(
        content=MARKDOWN.replace("doc-test-press-tp100-rev-a", "Bad ID!").encode()
    )
    bad_date = stack.upload(content=MARKDOWN.replace("2026-01-15", "15/01/2026").encode())
    bad_type = stack.upload(
        content=MARKDOWN.replace("revision: Rev. A", "revision: Rev. A\ndoc_type: exe").encode()
    )

    assert {no_meta.status_code, bad_id.status_code, bad_date.status_code} == {422}
    assert bad_type.status_code == 422
    assert stack.documents.documents == {}


def test_a_document_id_cannot_be_moved_to_other_equipment(stack):
    stack.upload()
    hijack = MARKDOWN.replace("eq-test-press-tp100", "eq-other-machine-x1")

    response = stack.upload(content=hijack.encode())

    assert response.status_code == 422
    assert stack.documents.documents["doc-test-press-tp100-rev-a"].equipment_id == (
        "eq-test-press-tp100"
    )


def test_a_superseded_upload_is_stored_but_not_current(stack):
    stack.upload(content=MARKDOWN.replace("Rev. A\n", "Rev. A\nstatus: superseded\n", 1).encode())

    assert stack.documents.documents["doc-test-press-tp100-rev-a"].status == "superseded"
    assert asyncio_run(stack.documents.list_current_document_ids()) == []


def test_an_oversized_upload_is_rejected_with_413():
    stack = DocStack(upload_max_bytes=2000)

    response = stack.upload(content=MARKDOWN.encode() + b"x" * 5000)

    assert response.status_code == 413


def test_an_indexing_failure_is_recorded_against_the_document(stack):
    async def broken_embed(texts):
        raise ConnectionError("embedding service down")

    stack.llm.embed = broken_embed

    body = stack.upload().json()
    (row,) = stack.client.get("/documents", headers=stack.auth("admin1")).json()

    assert body["status"] == "failed" and "embedding service down" in body["error"]
    assert row["ingestion_status"] == "failed"
    assert "embedding service down" in row["ingestion_error"]


def asyncio_run(coro):
    import asyncio

    return asyncio.run(coro)
