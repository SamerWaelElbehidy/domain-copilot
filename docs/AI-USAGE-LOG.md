# AI usage log

The brief asks for honesty: what was delegated, what was done by hand, where the AI misled, and how it was verified. A log that claims flawless
usage tells the reader nothing, so this one lists the mistakes.

**Who did what.** The candidate chose to have the AI assistant (Claude Code) write the code and explain its reasoning as it went, so that
they could learn from it and defend it. The candidate made the decisions below and reviewed and directed the work; the assistant wrote nearly all of the code, tests
and documentation. Where a statement would only be true of the candidate personally (hours spent, what they read line by line), it is left for them to complete in the last section, because the assistant cannot
know it.

## 1. What was delegated

| Area | Delegated to the AI | Human decision or check |
|---|---|---|
| Understanding the brief | Explained the brief, derived the variant, proposed a plan | The candidate confirmed the variant (D5, T4) and asked for every choice to be explained |
| Stack and architecture | Proposed Clean Architecture, Python and FastAPI, Postgres plus Qdrant, Ollama, and ADR text | The candidate accepted Python ("do what you think is right") and asked to be told if something fits better |
| Corpus | Wrote the 30 synthetic documents, including a superseded revision, LOTO cards, bulletins, policies and adversarial fixtures | Synthetic only, by the brief's rules |
| Ingestion and retrieval | Chunking, PDF and Markdown ingestion, hybrid retrieval with rank fusion | Reviewed through the evaluation numbers |
| Agents, orchestrator, approval gate | Three agents, five tools, state machine, hash-chained log, replay, signed approval token | |
| Evaluation | Golden set, harness, metrics, baseline runs, failure analysis | The candidate decided to build tools and agents first and the evaluation second |
| API, UI, security | Routes, roles, middleware, PII redaction, upload validation, the plain-JavaScript UI | |
| Packaging and CI | Dockerfile, compose, bootstrap script, CI workflow | The candidate asked the assistant to install Docker, then to fix it and to free disk space on `C:`, approving what could be deleted or moved |
| Documentation | BRD, system design, architecture, security, this log, the README | |
| Language scope | | The candidate decided the product would be **English only** for now ("continue in English only"), after the assistant offered Arabic support for the Damietta context |

## 2. What was not delegated

Decisions of scope and priority (variant, English only, order of work, which risks to accept), approval of environment changes (installing Docker, deleting or moving files to free disk space), and the
choice to keep failures visible in the evaluation and this log. Videos and the teaching delivery are the candidate's own.

## 3. Where the AI was wrong, and how it was caught

Each entry: what happened, how it was found, what changed.

| # | Mistake | How it was caught | Fix |
|---|---|---|---|
| 1 | **Placeholder copying.** The first answer prompt asked the model to cite `chunk_id` strings. The 1B model copied the `<chunk_id>` placeholder literally, so every answerable question was refused | The first evaluation run: 0% accuracy | Number the excerpts; the model cites 1 to N and code maps back to real chunks |
| 2 | **A lenient metric.** The accuracy metric credited a correct citation even when the answer was "1", "Paris" or an invented "1200Nm". It read 64% next to a mean groundedness of 0.08 | The two numbers contradicting each other | Answer words must be supported by the cited text; numbers and units count as support. Documented in the evaluation |
| 3 | **A tokenizer bug.** "minutes." and "minutes" did not match, so correct answers scored as unsupported | Reading individual failing cases instead of trusting the aggregate | Normalised punctuation; regression test |
| 4 | **Overlapping test cases.** A golden question collided with a conflicting-source fixture, so it measured the wrong thing | Reading the case list after an odd result | Replaced the question |
| 5 | **A confident wrong safety value.** The system quoted a value from a contradicting memo instead of the manual | The evaluation's conflicting-source cases, recorded as a failure in the baseline | A conflict guard. Its first version raised six false positives on the real corpus and was narrowed |
| 6 | **A weak approval gate.** The first gating design was easier to bypass than it should have been. The automated reviewer (Sourcery) flagged it on a pull request that had already merged | The bot's review comments | Rebuilt as an HMAC-signed token bound to one work order, issued only from `decide()`, with unsupported schema types rejected at registration. One suggestion, gating every side-effecting tool, was declined with a reason: `draft_work_order` only creates a draft |
| 7 | **Non-determinism.** The same injection payload was obeyed in one run and resisted in the next, so runs were not comparable | Comparing two runs of the same configuration | Temperature 0 and a fixed seed |
| 8 | **Dependencies missing from `requirements.txt`** (`pyjwt`, `python-multipart`) | CI's build validation, which imports every module | Added; later split into runtime and dev requirements with a lockfile |
| 9 | **Secrets in test files.** Test JWT secrets written as literals were flagged by the secret scanner | CI's gitleaks job | Tests generate their secrets at run time; a narrow allowlist covers the two exact strings already committed |
| 10 | **Infrastructure assumptions.** A Qdrant client and server of mismatched versions; a local Postgres already owning port 5432; Ollama cold-start timeouts that killed a whole evaluation run | Live runs against the real stack | Pinned matching versions, moved Postgres to 5433, per-case error isolation and longer timeouts |
| 11 | **A claim in the documentation that the code did not support.** The architecture document said the provider swap "touched nothing" outside `infrastructure/`, but the change also carried a `provider` field through application code | Re-reading each doc sentence against the diff | Reworded to say exactly what changed. Similarly, "base images pinned by tag" was corrected to "pinned to a tag, not a digest" |
| 12 | **A migration that could not run.** Migration 0008 re-added `runs.created_by`, which 0006 had created. All 285 tests passed and it merged, because no test touched a database | The assistant re-reading its own change; then proven by design: the first real-database CI run | Replaced with an index-only migration; a static test rejects duplicates; CI now runs migrations against Postgres; a hook blocks editing committed migrations |
| 13 | **A Windows-only dependency in the lockfile** (`pywin32`) | CI's Docker build failing | Removed; documented "generate lockfiles on Linux" |
| 14 | **A test that assumed instead of checked.** A database test asserted that creating a duplicate username raises. The real, deliberate behaviour is `ON CONFLICT DO NOTHING` (idempotent seeding, no silent role promotion) | The first real-database run | Test rewritten to assert the safer behaviour |
| 15 | **Runs were not attributed.** Background workflow tasks made model calls with no user or run id, so per-run cost was blank | Reviewing the observability requirement against the code | Usage context set inside the task; trace returns per-run totals; test added |
| 16 | **Docker Desktop would not start, three separate times.** The automated install hung on a permission prompt the assistant could not answer; the engine then failed because `C:` had under 2 GB free; later it crashed on a stale `engine.sock` file left by an earlier crash, and again the next day | Reading Docker's own log, which named the exact file each time, rather than guessing | Moved Docker's WSL data to another drive, removed the stale socket through WSL, freed about 32 GB on `C:`; the README troubleshooting lists the socket fix |
| 17 | **Shell-tool friction.** Heredocs with quotes failed to parse in the assistant's Windows shell; a few edits were retried through script files | Immediate errors | Write files with the editor tool; noted in `CLAUDE.md` |

## 4. How outputs were verified

- **Tests, including proof that they can fail.** New tests were run against deliberately broken code (a vendor import in `application/`, a duplicated migration column) to confirm they catch the problem.
- **The evaluation harness**, with bad numbers recorded (accuracy 55% with the 1B model, 73% with the 3B model, 23% false refusals) and each change measured against the previous run.
- **CI on every pull request**: build (including the Docker image), lint, tests against a real Postgres, dependency audit, secret scan over the full history.
- **Reading individual cases** instead of trusting aggregates (entries 2, 3, 4).
- **Checking documentation sentences against the code** (entry 11).
- **Not claiming what was not run.** Two things were never run and are listed as gaps everywhere they matter: the hosted-provider adapter against a real API (no key), and the web UI in a real browser.

## 5. Sections only the candidate can complete

Before submission the candidate should replace this section with their own words. Suggested content, so that nothing here is claimed on their behalf:

- Actual hours spent, and how they were split between reading, directing the assistant, reviewing and running the system.
- Which parts they read line by line and which they only ran, and which parts they can already explain without notes.
- One or two places where they overruled or corrected the assistant themselves.
- What they would ask the assistant to redo if they started again.
