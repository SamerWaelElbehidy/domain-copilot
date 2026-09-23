import re


def clean_text(text: str) -> str:
    """Clean stage (FR-1): normalizes whitespace without touching the
    Markdown structure (headings, numbered lists) that chunking depends
    on (ADR-0002)."""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()
