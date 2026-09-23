from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class ExtractedDocument:
    metadata: dict[str, str]
    body: str


_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n(.*)$", re.DOTALL)


def extract_markdown_document(raw_text: str) -> ExtractedDocument:
    """Extract stage (FR-1) for the Markdown input format: pulls the YAML
    frontmatter into metadata and returns the Markdown body untouched --
    chunking (ADR-0002) needs the heading/list structure intact, so
    extraction must not flatten it."""
    match = _FRONTMATTER_RE.match(raw_text)
    if not match:
        return ExtractedDocument(metadata={}, body=raw_text.strip())

    frontmatter_block, body = match.groups()
    metadata: dict[str, str] = {}
    for line in frontmatter_block.splitlines():
        if not line.strip() or ":" not in line:
            continue
        key, _, value = line.partition(":")
        metadata[key.strip()] = value.strip()

    return ExtractedDocument(metadata=metadata, body=body.strip())
