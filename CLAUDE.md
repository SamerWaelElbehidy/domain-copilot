# Project instructions for AI assistants

This is the D5T4 "Domain Copilot" assessment project: an agentic RAG platform for industrial field maintenance. These rules
encode the architecture and the lessons of building it. Read them before changing anything. The reasons are in `docs/`.

## Architecture rules (enforced by `tests/unit/test_architecture.py`; a violation fails the build)

- Layers: `domain/` -> nothing but the standard library. `application/` -> `domain/` only. `infrastructure/` -> `application/` and `domain/`.
  `api/` -> all of them. **Only `api/main.py` may name a concrete adapter.**
- `domain/` and `application/` must never import an LLM SDK, vector-store SDK, HTTP client, database driver, web framework, JWT or PDF library.
  New capability means a **port** in `application/ports/` and an **adapter** in `infrastructure/`.
- Swapping a provider must need configuration plus one adapter. If your change edits business logic to make a provider work, stop and rethink.

## Safety rules (the core of the D5 domain; never weaken these)

- The safety checklist of a work order is **copied by code** from a complete fetch of the current manual. Never take it from model output. A fetch that could be truncated fails closed.
- Nothing is dispatched without a supervisor's approval. The gated tool takes a signed `ApprovalToken` bound to one work order, issued only from the orchestrator's `decide()`.
  Do not add a boolean "approved" parameter, and do not list gated tools to agents.
- A reviewer may add safety steps, never remove them. The person who raised a run cannot approve it. Admins cannot approve dispatch.
- Superseded manual revisions are never used to answer or plan.
- Refusal ("not enough information") is a correct result. Never make the system answer more often by weakening a guard without measuring it (see Evaluation).

## Security rules

- No secrets in the repository, ever. Use `.env.example` placeholders. Tests generate secrets at run time.
- All SQL is parameterised. Never build SQL, shell commands or file paths from user or model text.
- The UI inserts text as text nodes. Never use `innerHTML`, `outerHTML`, `insertAdjacentHTML`, `document.write` or `eval` (a test forbids them). No inline scripts or styles (strict CSP).
- Personal data is redacted (`application/pii.py`) before storage and before any model call. Never log values, only kinds and counts.
- Every new tool needs a JSON schema, an agent allow-list entry, and a contract test. Tool arguments are validated before execution.
- Any new endpoint states its required permission and ownership rule, with a test for the forbidden case (403 or 404).

## Database rules

- **Migrations are history.** Never edit a committed migration (a hook blocks it). Add the next numbered file. `tests/unit/test_migrations.py` rejects duplicate tables, columns and indexes,
  and CI applies every migration to a real Postgres.
- `run_steps` is an append-only audit log (trigger plus hash chain). Never add code that updates or deletes it.

## Prompts and evaluation

- Prompts are versioned files in `prompts/`. **Never edit a released prompt.** Add `name.vN+1.md`, point the code at it, and re-run `python scripts/evaluate.py`.
- A change that touches retrieval, prompts, guards or models is measured with the golden set and the numbers go in `docs/EVALUATION.md`, including any that got worse.
  Do not tune the relevance threshold on the same questions you report.

## How to work

- Branch from `main`, never commit to it. Conventional Commits (`feat:`, `fix:`, `docs:`, `test:`, `chore:`), messages explain **why**. Atomic commits. One pull request per concern, with what, why, how tested.
  Branch protection needs the branch up to date and CI green.
- Commit trailer: `Co-Authored-By: Claude <noreply@anthropic.com>` (use the model name from the session).
- Quality gate before every push: `python -m ruff check src tests scripts` and `python -m pytest tests -q` (the `/check` command runs both).
- Prefer in-memory fakes with real behaviour (`tests/fakes/`) over mock objects. LLM calls are stubbed in unit tests. Ten sharp tests beat a hundred trivial ones.
- **Never claim a feature that does not exist**, in code comments, docs or PR text. If something was not run, say it was not run. Update the gap table in `docs/SYSTEM-DESIGN.md` when you cut scope.
- Verify your own claims: after writing a doc sentence about the code, check it against the code. A wrong sentence in the docs is worse than a missing one.

## Commands

```bash
python -m ruff check src tests scripts          # lint
python -m pytest tests -q                        # tests (live-service tests skip themselves)
docker compose up -d postgres                    # then the Postgres suite runs too
python scripts/evaluate.py --label my-run        # golden-set evaluation (needs the full stack)
docker compose up --build                        # everything, with models and demo data
```

## Environment notes (Windows development machine)

- Bash heredocs containing quotes or `$` sometimes fail to parse in the assistant's shell tool. Write the file with the editor tool, or a script file, instead.
- Generate lockfiles on Linux or in the Docker build. A lockfile made on Windows once included `pywin32` and broke the image.

## Where things are

`docs/ARCHITECTURE.md` (diagrams), `docs/SYSTEM-DESIGN.md` (decisions and gap table), `docs/SECURITY.md` (controls), `docs/EVALUATION.md` (numbers), `docs/adr/` (why).
