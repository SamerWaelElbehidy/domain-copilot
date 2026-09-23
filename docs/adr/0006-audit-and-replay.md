# ADR-0006: Replay from persisted state, not by re-calling the LLM; hash-chained steps

## Status
Accepted

## Context
Our assigned twist, **T4 (Audit & replay)**, requires: runs persisted in
enough detail to replay deterministically, a `replay <run-id>` command,
and — as a plus — a tamper-evident log. This overlaps with, and extends,
FR-9's baseline observability requirement (correlation ID, per-request
token/cost accounting, inspectable-by-run-ID).

The word "deterministically" is the hard constraint. LLMs are not
deterministic (temperature > 0 by design, and even temperature 0 can
drift across model versions/provider infra). So "replay" cannot mean
"re-send the same prompts and expect the same output" — that would be
replaying the *request*, not the *run*.

## Decision
**Replay reconstructs a run entirely from persisted `RunStep` records —
it never calls an LLM, vector store, or tool again.**

Every step in a `Run` (ADR-0005) is captured as a `RunStep`:

```
step_index, name, agent_name, provider_used,
input_snapshot   (exact messages/tool-args sent),
output_snapshot  (completion text / tool result / retrieved chunk IDs+scores),
input_tokens, output_tokens, started_at, finished_at, status,
step_hash
```

`replay <run-id>` loads all `RunStep`s for that run in order and re-plays
their recorded `output_snapshot`s through the same presentation path a
live run would use (e.g. the streaming UI), so a grader watches the exact
recorded sequence of agent actions, tool calls, retrieved chunks, and the
approval decision — byte-for-byte reproducible, because nothing is
regenerated.

**Tamper-evident log (the "plus").** Each `RunStep.step_hash` is a SHA-256
over `{step_index, name, output_snapshot, previous_step_hash}` — a hash
chain, the same idea as a git commit chain or a naive blockchain. On
replay (and on any audit read), we recompute the chain and compare; a
mismatch means a persisted step was edited after the fact. This needs no
extra infrastructure (no external ledger), just a pure function in the
domain layer (`compute_step_hash`, alongside `RunStep`).

**Cost/observability reuse.** `RunStep.provider_used` and
`input_tokens`/`output_tokens` double as FR-9's per-request token and
cost accounting — we do not maintain a second log for that; the audit
trail *is* the cost ledger, queried differently depending on the need.

## Alternatives considered
- **Replay by re-invoking the LLM with recorded inputs** — simpler to
  explain, but violates "deterministically": two replays could show two
  different agent behaviors, and worse, could silently diverge from what
  the human supervisor actually approved. Rejected outright — this would
  misrepresent what happened, which is exactly the kind of honesty gap
  the brief is checking for.
- **Event sourcing the entire system** (not just runs) — architecturally
  elegant, but out of scope for 40 hours; only `Run`/`RunStep` need this
  discipline, not `Equipment`/`ManualDocument`, which are simple CRUD-ish
  aggregates with no replay requirement. Documented as a Part-A
  (unconstrained target architecture) idea in `docs/SYSTEM-DESIGN.md`,
  not built now.
- **External tamper-evident log (e.g. a real ledger/Merkle service)** —
  correctly out of scope for a free-tier, single-node submission; the
  hash chain gives the same tamper-*evidence* property (an edit is
  detectable) without tamper-*prevention* infrastructure, which is an
  honest, documented gap for `docs/SYSTEM-DESIGN.md` Part B.

## Consequences
- `input_snapshot`/`output_snapshot` must never contain secrets (API
  keys) — only the request/response content itself. Cross-checked against
  `docs/SECURITY.md`'s "auditable logging that never records secrets"
  control once written.
- Every agent/tool call in the system must go through the step-recording
  wrapper — an agent that calls a tool "on the side" without recording a
  `RunStep` breaks both audit and replay. This becomes a code-review rule,
  noted in `docs/AGENTIC-WORKFLOW.md`.
- Storage grows with `input_snapshot`/`output_snapshot` size (full
  message history and retrieved chunk content per step). Acceptable for
  this submission's scale (30-some documents, a bounded eval set); flagged
  as a Part-A scaling concern (would move to blob storage + a pointer at
  higher volume).
