"""Builds small valid text PDFs for tests, so PDF ingestion is tested on real
PDF bytes without adding a rendering dependency."""

from __future__ import annotations

import textwrap

LINES_PER_PAGE = 46
_ASCII = {"—": "-", "–": "-", "’": "'", "‘": "'", "“": '"', "”": '"'}


def _escape(text: str) -> str:
    text = "".join(_ASCII.get(ch, ch) for ch in text).encode("ascii", "replace").decode()
    return text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def build_pdf(pages: list[list[str]]) -> bytes:
    """Each page is a list of text lines, drawn top to bottom in Helvetica."""
    objects: list[bytes] = []

    def add(body: str | bytes) -> int:
        objects.append(body.encode() if isinstance(body, str) else body)
        return len(objects)

    add("<< /Type /Catalog /Pages 2 0 R >>")
    add("")  # pages object, filled in below
    add("<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")
    page_ids: list[int] = []
    for lines in pages:
        ops = ["BT", "/F1 10 Tf", "50 780 Td", "14 TL"]
        ops += [f"({_escape(line)}) Tj T*" for line in lines]
        ops.append("ET")
        stream = "\n".join(ops).encode()
        content_id = add(b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream")
        page_ids.append(
            add(
                "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
                f"/Contents {content_id} 0 R /Resources << /Font << /F1 3 0 R >> >> >>"
            )
        )
    kids = " ".join(f"{i} 0 R" for i in page_ids)
    objects[1] = f"<< /Type /Pages /Kids [{kids}] /Count {len(page_ids)} >>".encode()

    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for number, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += f"{number} 0 obj\n".encode() + body + b"\nendobj\n"
    xref_at = len(out)
    out += f"xref\n0 {len(objects) + 1}\n".encode() + b"0000000000 65535 f \n"
    for offset in offsets:
        out += f"{offset:010d} 00000 n \n".encode()
    out += (
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref_at}\n%%EOF\n"
    ).encode()
    return bytes(out)


def manual_pdf(markdown: str, header: str = "Dawlia Furniture Works - Maintenance Manual") -> bytes:
    """Renders a corpus Markdown manual the way a typical exported PDF looks:
    plain heading lines, wrapped paragraphs, a running header and page numbers."""
    body = markdown.split("---", 2)[2] if markdown.startswith("---") else markdown
    lines: list[str] = []
    for raw in body.splitlines():
        text = raw.lstrip("# ").rstrip() if raw.startswith("#") else raw.rstrip()
        if not text.strip():
            continue
        wrapped = textwrap.wrap(text, width=88, subsequent_indent="   ")
        lines += wrapped or [""]
    pages = [lines[i : i + LINES_PER_PAGE] for i in range(0, len(lines), LINES_PER_PAGE)]
    return build_pdf(
        [[header, *page, f"Page {n}"] for n, page in enumerate(pages, start=1)]
    )
