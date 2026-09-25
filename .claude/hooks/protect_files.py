"""PreToolUse hook: refuse edits that must never happen silently.

Two rules, both learned the hard way in this project:

1. Never write real secrets: `.env` and key files are off limits (only
   `.env.example` may be edited).
2. Never edit a migration that is already committed. Migrations are history;
   a fix is a new migration. (Migration 0008 once re-added a column that 0006
   had created; editing applied migrations is how databases drift.)

Reads the tool-call JSON from stdin. Exit status 2 blocks the call and tells the
assistant why.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def committed(path: Path) -> bool:
    result = subprocess.run(
        ["git", "ls-files", "--error-unmatch", str(path)],
        capture_output=True,
        check=False,
    )
    return result.returncode == 0


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except json.JSONDecodeError:
        return 0
    file_path = (payload.get("tool_input") or {}).get("file_path", "")
    if not file_path:
        return 0
    path = Path(file_path)
    name = path.name

    if (name == ".env" or name.startswith(".env.")) and name != ".env.example":
        sys.stderr.write(
            "Blocked: do not write real environment files. Put placeholders in .env.example.\n"
        )
        return 2
    if path.suffix in {".pem", ".key"}:
        sys.stderr.write("Blocked: key files never belong in this repository.\n")
        return 2
    if path.parent.name == "migrations" and path.suffix == ".sql" and committed(path):
        sys.stderr.write(
            f"Blocked: {name} is already committed. Add a new numbered migration instead of "
            "editing history.\n"
        )
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
