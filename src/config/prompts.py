"""Prompts are versioned artifacts on disk (brief section 4), not string
literals. The returned hash is recorded in run steps so an audit can tell
which prompt text produced a given output."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

PROMPTS_DIR = Path(__file__).resolve().parents[2] / "prompts"


@dataclass(frozen=True)
class Prompt:
    name: str
    version: str
    text: str

    @property
    def sha256(self) -> str:
        return hashlib.sha256(self.text.encode("utf-8")).hexdigest()

    @property
    def label(self) -> str:
        return f"{self.name}.{self.version}"


def load_prompt(name: str, version: str = "v1") -> Prompt:
    path = PROMPTS_DIR / f"{name}.{version}.md"
    return Prompt(name=name, version=version, text=path.read_text(encoding="utf-8").strip())
