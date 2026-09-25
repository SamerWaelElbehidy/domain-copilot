from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile

from api.container import Container
from api.deps import current_user, get_container, require
from application.use_cases.upload_document import upload_document
from domain.entities.user import User
from domain.value_objects.role import Permission

router = APIRouter(tags=["documents"])
_can_ingest = require(Permission.INGEST_DOCUMENTS)


def _ready(container: Container) -> None:
    if container.ingestion is None or container.documents is None:
        raise HTTPException(status_code=503, detail="ingestion is not configured")


@router.post("/documents", status_code=201)
async def upload(
    file: UploadFile = File(...),
    equipment_id: str | None = Form(default=None, max_length=64),
    equipment_name: str | None = Form(default=None, max_length=200),
    document_id: str | None = Form(default=None, max_length=64),
    revision: str | None = Form(default=None, max_length=32),
    effective_date: str | None = Form(default=None, max_length=10),
    doc_type: str | None = Form(default=None, max_length=16),
    status: str | None = Form(default=None, max_length=16),
    user: User = Depends(_can_ingest),
    container: Container = Depends(get_container),
) -> dict[str, Any]:
    """Admin-only. PDF or Markdown, size-capped by middleware and type-checked
    from the bytes. For Markdown the metadata is in the file's frontmatter;
    for PDF it comes from these form fields."""
    _ready(container)
    content = await file.read()
    metadata = {
        "equipment_id": equipment_id, "equipment_name": equipment_name,
        "document_id": document_id, "revision": revision, "effective_date": effective_date,
        "doc_type": doc_type, "status": status,
    }
    report = await upload_document(
        filename=file.filename or "",
        content=content,
        metadata={k: v for k, v in metadata.items() if v},
        **container.ingestion.__dict__,  # type: ignore[union-attr]
    )
    return {**report.__dict__, "uploaded_by": user.username}


@router.get("/equipment")
async def list_equipment(
    _: User = Depends(current_user), container: Container = Depends(get_container)
) -> list[dict[str, str]]:
    """Equipment the copilot knows about, for the question filter."""
    _ready(container)
    return [
        {"equipment_id": e.equipment_id, "name": e.name}
        for e in await container.documents.list_equipment()  # type: ignore[union-attr]
    ]


@router.get("/documents")
async def list_documents(
    _: User = Depends(_can_ingest), container: Container = Depends(get_container)
) -> list[dict[str, Any]]:
    """Per-document ingestion status with failure reasons (FR-1)."""
    _ready(container)
    rows = await container.documents.list_with_status()  # type: ignore[union-attr]
    return [
        {
            "document_id": r.document.document_id,
            "equipment_id": r.document.equipment_id,
            "revision": r.document.revision,
            "title": r.document.title,
            "doc_type": r.document.doc_type,
            "status": r.document.status,
            "ingestion_status": r.ingestion_status,
            "ingestion_error": r.ingestion_error,
        }
        for r in rows
    ]
