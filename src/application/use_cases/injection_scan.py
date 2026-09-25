from __future__ import annotations

import re

# Heuristic scan for text that addresses an AI system instead of a technician.
# It is one defence-in-depth layer, not a proof: a determined attacker can
# rephrase. Retrieved text is also fenced off from instructions in the prompt,
# every answer must be supported by its citations, and a human approves
# anything consequential.
_PATTERNS = [
    r"\b(ignore|disregard|forget|override)\b.{0,60}\b(previous|prior|earlier|above|all|any)\b"
    r".{0,60}\b(instruction|instructions|rule|rules|prompt|safety)\b",
    r"\b(notice|note|message|instruction|instructions|memo)s?\s+(to|for)\s+(the\s+)?"
    r"(ai|a\.i\.|assistant|assistants|copilot|copilots|llm|model|models|bot)\b",
    r"\b(ai|llm)\s+(assistant|assistants|copilot|model|system)s?\b",
    r"\bsystem\s+(instruction|instructions|prompt|override|message|notice)\b",
    r"\b(begin|start|prefix)\s+(every|each|all)\s+(answer|response|reply)\b",
    r"\b(do not|don't|must not|never)\s+(disclose|reveal|mention|tell)\b.{0,50}"
    r"\b(instruction|memo|line|message|notice)\b",
    r"\byou\s+(must|should|are required to)\s+(tell|say|state|answer|respond)\b",
    r"\bassistants?\s+(reading|processing|answering)\b",
]
_COMPILED = [re.compile(p, re.IGNORECASE | re.DOTALL) for p in _PATTERNS]


def looks_like_prompt_injection(text: str) -> bool:
    return any(p.search(text) for p in _COMPILED)


def matching_patterns(text: str) -> list[str]:
    return [p.pattern for p in _COMPILED if p.search(text)]
