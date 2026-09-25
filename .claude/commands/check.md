---
description: Run the full local quality gate (lint, tests, migrations, compose validation) and summarise the result
---

Run the project's quality gate from the repository root and report the outcome honestly.

1. `python -m ruff check src tests scripts`
2. `python -m pytest tests -q` (note how many tests were skipped and why: live-service tests skip when Postgres, Qdrant or Ollama are absent)
3. `docker compose config -q`
4. `python -m compileall -q src scripts`

If Postgres is running (`docker compose ps postgres`), state whether the Postgres suite ran. If any step fails, show the failing output, find the cause, and fix it.
Do not weaken a test, skip a check or edit `.gitleaks.toml` to get green. Finish with one line per step: passed, failed or skipped (and why).
