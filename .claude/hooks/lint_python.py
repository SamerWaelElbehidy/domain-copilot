"""PostToolUse hook: lint every Python file the assistant edits.

Reads the tool-call JSON from stdin. If the edited file is Python under src/,
tests/ or scripts/, runs ruff on it. On findings it exits with status 2 and
prints them to stderr, which Claude Code feeds back to the assistant so it fixes
the problem in the same turn instead of leaving it for CI.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except json.JSONDecodeError:
        return 0
    file_path = (payload.get("tool_input") or {}).get("file_path", "")
    path = Path(file_path)
    if path.suffix != ".py" or not path.exists():
        return 0
    if not any(part in {"src", "tests", "scripts"} for part in path.parts):
        return 0
    result = subprocess.run(
        [sys.executable, "-m", "ruff", "check", str(path)],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        sys.stderr.write(f"ruff found problems in {path.name}; fix them before continuing:\n")
        sys.stderr.write(result.stdout or result.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
