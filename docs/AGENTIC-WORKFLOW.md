# Agentic coding workflow

This project was built with an AI assistant (Claude Code) as a governed participant, not as autocomplete. This document says what was
configured, why, what it changed, and where the approach failed. The configuration is committed: [`CLAUDE.md`](../CLAUDE.md) and
[`.claude/`](../.claude). What was delegated and what went wrong, item by item, is in [AI-USAGE-LOG.md](AI-USAGE-LOG.md).

**A timing note, stated plainly.** Most of the code existed before these files were committed. Until then the same rules were given to the assistant in
conversation, and several of them were written *because* of a failure recorded below. Committing them turned habits into mechanisms:
the architecture rule became a test, the "do not edit applied migrations" rule became a hook. What the files demonstrably changed is what happened
after they existed. I do not claim they shaped the earlier commits.

## The configured items

| # | Item | Where | What it does |
|---|---|---|---|
| 1 | **Project instruction file** | [`CLAUDE.md`](../CLAUDE.md) | Encodes the architecture rules, safety rules, security rules, database rules, prompt and evaluation rules, and the working conventions |
| 2 | **Sub-agents scoped to distinct roles** | [`.claude/agents/`](../.claude/agents) | `security-reviewer` (read-only), `test-writer`, `docs-writer` |
| 3 | **Hooks enforcing quality gates automatically** | [`.claude/settings.json`](../.claude/settings.json), [`.claude/hooks/`](../.claude/hooks) | A pre-edit hook refuses edits to committed migrations and to real `.env` or key files; a post-edit hook lints every Python file the assistant touches and feeds the findings back in the same turn |
| 4 | **Custom commands for repeated operations** | [`.claude/commands/`](../.claude/commands) | `/check` (the quality gate), `/adr` (draft an ADR), `/eval` (run and compare the evaluation) |
| 5 | **A versioned prompt library for the product** | [`prompts/`](../prompts) | `answer_question.v1..v3` and one prompt per agent, loaded by name and version with a content hash |
| 6 | **Rules made executable** (beyond the five categories) | [`tests/unit/test_architecture.py`](../tests/unit/test_architecture.py), [`tests/unit/test_migrations.py`](../tests/unit/test_migrations.py), [`tests/unit/test_agentic_hooks.py`](../tests/unit/test_agentic_hooks.py) | The dependency rule, the migration rule and the hooks themselves are tested, so the AI cannot quietly break the boundary it was told about |

Not used: MCP servers, and a custom MCP server. The assistant's built-in file, shell and browser tools were enough; I would rather list this than pad the table.

## 1. The project instruction file

**Why.** An assistant that has not been told the architecture will happily import `httpx` into a use case because it is the shortest path. The brief's central
engineering rule (domain and application layers never depend on an SDK or a framework) is exactly the kind of boundary that erodes one convenient import at a time.
`CLAUDE.md` states it, and, more importantly, states the **safety** rules that must never be traded for convenience: the checklist is copied by code, nothing dispatches without a signed approval,
refusal is a correct answer, and never claim what does not exist.

**What it changed.** Every session starts from the same rules instead of whatever the last conversation left behind. It also holds environment lessons (Windows shell quirks, Linux-generated lockfiles).
**What it did not do:** a rule in prose does not stop an assistant that misreads it. That is why item 6 exists.

## 2. Sub-agents

**Why separate roles.** The reviewer must not be the author. A single assistant asked to "write this and check it is secure" tends to confirm its own work.
`security-reviewer` is read-only (no edit tools) and works from a checklist derived from this project's own threat model. `test-writer` is told to prove the **forbidden** case and to break the code
on purpose to see the test fail. `docs-writer` is told to verify every sentence against the code.

**What it changed / honest status.** The three agents are defined and their instructions encode lessons from real failures (below). I did not run a controlled comparison, so I cannot say how much they improved the work.
The evidence I can point to is indirect: the doc claims that were corrected during this project (for example, an over-stated "touches nothing" claim about the provider swap, and "pinned by tag" written where the base images are pinned to a tag, not a digest)
were caught by checking sentences against code, which is the discipline the `docs-writer` prompt now demands.

## 3. Hooks

**Why.** A reminder can be ignored; a hook cannot.

- `protect_files.py` (before an edit): blocks writing `.env` files and keys, and blocks editing a **committed** migration. This exists because migration 0008 re-added a column that 0006 had already created, which would have crashed the first real container start.
  Migrations are history; a fix is a new file.
- `lint_python.py` (after an edit): runs ruff on the edited file and returns status 2 with the findings, so the assistant fixes lint in the same turn rather than discovering it in CI.

**What it changed.** Lint failures reach the assistant immediately instead of after a push. The migration rule can no longer be broken by accident. Both hooks are tested ([`test_agentic_hooks.py`](../tests/unit/test_agentic_hooks.py)), including malformed input.
**Limit:** hooks only run in a Claude Code session with this repository's settings. They are not a substitute for CI, which runs the same lint and the tests for everyone.

## 4. Commands

`/check` runs the same gate as CI locally and requires an honest one-line result per step, including what was skipped and why (live-service tests skip when their service is absent, and an assistant that reports "all green" without saying so is hiding something).
`/adr` forces the ADR structure with **why each alternative was rejected**. `/eval` re-runs the golden set and requires reporting the metrics that got *worse*, and forbids tuning on the reported questions.

## 5. The versioned prompt library

Prompts for the product are files, loaded by name and version, with a SHA-256 of the text available for the audit log. **Never edit a released prompt; add the next version and re-run the evaluation.**
The history is in the evaluation: `answer_question.v1` asked the model to copy `chunk_id` strings and scored 0% (the 1B model copied the placeholder literally); `v2` numbered the excerpts; `v3` requires a full sentence restating the fact with its unit, after the
metric showed the model answering "1" or "Paris". Each version exists because a measured failure demanded it ([EVALUATION.md](EVALUATION.md), section 4).

## 6. Rules made executable

- **Architecture test.** Parses every import in `domain/`, `application/` and `infrastructure/` and fails on an outer-layer or vendor import; only `api/main.py` may name a concrete adapter. Verified to fail when `import httpx` is added to `application/`.
- **Migration test.** Rejects duplicate tables, columns and indexes. Verified to fail on a deliberately duplicated column. CI additionally applies every migration to a real Postgres.
- **The UI safety test.** Forbids markup sinks and inline script or style in the UI, because the strict CSP would silently break them and a model-written line is where they would sneak in.

## How a change flows

1. Branch from `main`. The assistant reads `CLAUDE.md`.
2. It implements; the lint hook reports problems in the same turn; the migration hook stops history edits.
3. Tests are written to prove the forbidden case, then the code is broken on purpose to see them fail.
4. `/check` runs the gate. For anything touching routes, agents, retrieval, prompts or uploads, `security-reviewer` reviews the diff.
5. Pull request with what, why, how tested. CI runs build (including the Docker image), lint, tests against a real Postgres, dependency audit and a secret scan over history.
   An automated reviewer (Sourcery) comments on some pull requests.
6. Merge only when green and up to date (branch protection).

## Where the agentic approach failed

Details and how each was caught are in the [AI usage log](AI-USAGE-LOG.md). The patterns:

1. **Confident, wrong claims in prose.** The assistant wrote documentation sentences that were not true of the code (over-stated isolation, "pinned by tag"). Caught only by re-reading against the code. This is why the docs-writer rule is "verify every sentence".
2. **Tests that assume instead of check.** A database test asserted that creating a duplicate username raises; the real behaviour (deliberately `ON CONFLICT DO NOTHING`) is safer, and the first run against a real database showed the assumption was wrong.
3. **Passing tests are not a working system.** All 285 tests passed while a migration that could not run had been merged, because nothing touched a database. The lesson is a CI job that runs the real thing, which now exists.
4. **Metrics that flatter.** The first accuracy metric credited a cited chunk even when the answer was "Paris". The assistant wrote a harness that graded its own homework generously until the numbers looked implausible (0.08 mean groundedness next to 64% "accuracy").
5. **Optimising a number instead of the goal.** A conflict-detection guard first produced six false positives on the real corpus and had to be narrowed (same equipment, context overlap of at least three words). The relevance threshold was chosen from the same 35 cases the evaluation reports, which flatters the result; the evaluation lists this as a threat to validity.
6. **Cross-platform blind spots.** A lockfile generated on Windows included `pywin32`, and the assistant's shell tool mis-parsed some heredocs. CI's image build and the real-database suite caught what local runs did not.
7. **Things not run.** The hosted-provider adapter was never run against a real API (no key), and the web UI was never exercised in a real browser (the assistant's browser access was declined). Both are listed as gaps rather than claimed.

## What I would change with more time

- Run the security-reviewer sub-agent as a required step on pull requests (a CI job or a review command), rather than by convention.
- Add a hook that refuses a documentation claim about a file that does not exist (link and path checking).
- Record, per pull request, which parts were AI-written and which were reviewed by a human line by line, so the split is measured instead of remembered.
