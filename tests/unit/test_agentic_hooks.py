"""The agentic-workflow hooks are code that gates every AI edit, so they are
tested like any other code (docs/AGENTIC-WORKFLOW.md)."""

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HOOKS = ROOT / ".claude" / "hooks"


def run_hook(script: str, file_path: Path | str, cwd: Path = ROOT) -> subprocess.CompletedProcess:
    payload = json.dumps({"tool_input": {"file_path": str(file_path)}})
    return subprocess.run(
        [sys.executable, str(HOOKS / script)],
        input=payload, capture_output=True, text=True, cwd=cwd, check=False,
    )


def test_editing_an_already_committed_migration_is_blocked():
    result = run_hook("protect_files.py", ROOT / "migrations" / "0001_equipment_and_documents.sql")

    assert result.returncode == 2 and "new numbered migration" in result.stderr


def test_a_brand_new_migration_file_is_allowed():
    assert run_hook("protect_files.py", ROOT / "migrations" / "9999_new_change.sql").returncode == 0


def test_real_env_files_and_keys_are_blocked_but_the_example_is_not():
    assert run_hook("protect_files.py", ROOT / ".env").returncode == 2
    assert run_hook("protect_files.py", ROOT / ".env.production").returncode == 2
    assert run_hook("protect_files.py", ROOT / "deploy.pem").returncode == 2
    assert run_hook("protect_files.py", ROOT / ".env.example").returncode == 0


def test_ordinary_source_files_are_not_blocked():
    source = ROOT / "src" / "domain" / "entities" / "run.py"

    assert run_hook("protect_files.py", source).returncode == 0


def test_lint_hook_feeds_ruff_findings_back_with_status_2(tmp_path):
    bad = tmp_path / "src" / "bad.py"
    bad.parent.mkdir()
    bad.write_text("import os\n", encoding="utf-8")  # unused import

    result = run_hook("lint_python.py", bad)

    assert result.returncode == 2 and "F401" in result.stderr


def test_lint_hook_passes_clean_files_and_ignores_other_file_types(tmp_path):
    clean = tmp_path / "src" / "ok.py"
    clean.parent.mkdir()
    clean.write_text("VALUE = 1\n", encoding="utf-8")
    notes = tmp_path / "src" / "notes.md"
    notes.write_text("import os\n", encoding="utf-8")

    assert run_hook("lint_python.py", clean).returncode == 0
    assert run_hook("lint_python.py", notes).returncode == 0


def test_hooks_tolerate_malformed_input():
    for script in ("protect_files.py", "lint_python.py"):
        result = subprocess.run(
            [sys.executable, str(HOOKS / script)], input="not json", capture_output=True,
            text=True, cwd=ROOT, check=False,
        )
        assert result.returncode == 0
