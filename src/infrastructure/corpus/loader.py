from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from application.use_cases.ingestion.extract_markdown import extract_markdown_document
from domain.entities.equipment import Equipment
from domain.entities.manual_document import ManualDocument

_MODEL_RE = re.compile(r"\b[A-Z]{2,4}-\d{2,4}\b")


@dataclass(frozen=True)
class CorpusDocument:
    equipment: Equipment
    document: ManualDocument
    raw_text: str


def _doc_type(path: Path) -> str:
    if path.parent.name == "facility-wide":
        return "policy"
    if path.name.startswith("loto"):
        return "loto"
    if path.name.startswith(("service-bulletin", "memo")):
        return "bulletin"
    return "manual"


def load_corpus(root: Path) -> list[CorpusDocument]:
    """Turns the Markdown corpus into domain entities plus raw text. The
    frontmatter is the source of truth; doc_type comes from the file name
    convention documented in docs/CORPUS-MANIFEST.md."""
    documents: list[CorpusDocument] = []
    for path in sorted(root.rglob("*.md")):
        raw_text = path.read_text(encoding="utf-8")
        meta = extract_markdown_document(raw_text)
        fm, body = meta.metadata, meta.body
        title = next((ln[2:].strip() for ln in body.splitlines() if ln.startswith("# ")), path.stem)
        model = _MODEL_RE.search(fm["equipment_name"])
        documents.append(
            CorpusDocument(
                equipment=Equipment(
                    equipment_id=fm["equipment_id"],
                    name=fm["equipment_name"],
                    model_number=model.group(0) if model else "n/a",
                    category="industrial",
                ),
                document=ManualDocument(
                    document_id=fm["document_id"],
                    equipment_id=fm["equipment_id"],
                    revision=fm["revision"],
                    effective_date=date.fromisoformat(fm["effective_date"]),
                    title=title,
                    doc_type=_doc_type(path),
                    status=fm.get("status", "current"),
                ),
                raw_text=raw_text,
            )
        )
    return documents
