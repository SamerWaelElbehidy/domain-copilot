from __future__ import annotations

import re

_STOPWORDS = {
    "that", "this", "with", "from", "have", "must", "should", "before", "after", "when",
    "than", "then", "them", "they", "their", "there", "which", "while", "will", "your",
    "into", "only", "also", "such", "each", "every", "been", "being", "does", "were",
    "what", "where", "about", "above", "below", "other", "these", "those", "would",
}


def content_tokens(text: str) -> set[str]:
    words = (w.strip(".") for w in re.findall(r"[a-z0-9.]+", text.lower()))
    # Numbers and units ("40c", "30", "0.5") are the facts a technician acts on,
    # so short tokens containing a digit count; a lone digit ("1") does not.
    return {
        w
        for w in words
        if (len(w) >= 4 and w not in _STOPWORDS)
        or (len(w) >= 2 and any(ch.isdigit() for ch in w))
    }


def support_score(answer_text: str, cited_texts: tuple[str, ...] | list[str]) -> float:
    """Share of the answer's content words that also occur in the cited
    excerpts. A deterministic check that the answer's own text is backed by
    what it cites: it rejects degenerate answers ("1", "Paris") and invented
    values, but it cannot judge paraphrase or logic, so it complements rather
    than replaces human review."""
    answer_tokens = content_tokens(answer_text)
    if not answer_tokens:
        return 0.0
    support = content_tokens(" ".join(cited_texts))
    return len(answer_tokens & support) / len(answer_tokens)
