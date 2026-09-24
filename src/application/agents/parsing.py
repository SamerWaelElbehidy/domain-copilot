from __future__ import annotations

import json
import re
from typing import Any

from domain.errors.domain_errors import AgentOutputError

_FENCE = re.compile(r"^```(?:json)?\s*|\s*```$", re.MULTILINE)


def parse_json_object(text: str) -> dict[str, Any]:
    """Model output is untrusted: accept only a JSON object, tolerate code
    fences, reject everything else so callers never act on prose."""
    cleaned = _FENCE.sub("", text.strip())
    start, end = cleaned.find("{"), cleaned.rfind("}")
    if start == -1 or end <= start:
        raise AgentOutputError("model output contains no JSON object")
    try:
        parsed = json.loads(cleaned[start : end + 1])
    except json.JSONDecodeError as exc:
        raise AgentOutputError(f"model output is not valid JSON: {exc}") from exc
    if not isinstance(parsed, dict):
        raise AgentOutputError("model output JSON is not an object")
    return parsed
