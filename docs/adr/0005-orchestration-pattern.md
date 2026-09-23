# ADR-0005: State-machine orchestration

## Status
Accepted

## Context
FR-5 requires a named, justified orchestration pattern from: supervisor,
planner–executor, pipeline, state machine. D5's workflow is fixed and
known in advance — symptom → equipment/revision match → diagnostic
sequence → safety prerequisites → work order → human approval → dispatch
— executed by three named agents in a set order (Symptom Matcher →
Diagnostic & Safety Planner → Work Order Generator), not an open-ended
task an LLM plans dynamically.

## Decision
**State machine.** A `Run` (`src/domain/entities/run.py`) holds a
`RunState` and a `transition_to()` method that only allows moves present
in a fixed adjacency table (`RunState.py`) — the same enforcement style
already used by `WorkOrder` (ADR from the domain-entities commit): illegal
transitions raise `InvalidRunTransitionError` rather than silently
happening.

States: `RECEIVED → MATCHING_SYMPTOM → DIAGNOSING → DRAFTING_WORK_ORDER →
PENDING_APPROVAL → {APPROVED → DISPATCHED | REJECTED}`, with three
terminal escape states reachable from most in-progress states:
`REFUSED_LOW_EVIDENCE` (binding principle 1), `DEGRADED_PLAIN_RAG`
(graceful degradation), `FAILED` (unrecoverable).

**Why state machine over the alternatives:**
- **Supervisor** — an LLM decides which agent to call next in a loop.
  Rejected: our agent sequence is fixed by the domain pack table, not
  something we want an LLM improvising; a supervisor pattern would be
  solving a problem we don't have and would make replay (T4) harder to
  reason about, since "what happens next" would depend on a fresh LLM
  decision instead of being enumerable up front.
- **Planner–executor** — a planner drafts a multi-step plan, an executor
  runs it. Rejected for the same reason: planning implies the step
  sequence is discovered per-request; ours is fixed by design.
- **Pipeline** — closest cousin of our choice, and arguably what we have
  *within* a state's happy path. Chosen state machine over plain pipeline
  specifically because we need named, addressable non-happy-path states
  (refusal, degradation, rejection) with their own transition rules, not
  just "step 3 failed, stop" — a pipeline model handles the happy path
  well but under-specifies failure/refusal/approval branching.

**Mandatory controls (FR-5), where each lives:**
- *Max-iteration breaker* and *per-step timeout*: applied by the
  application-layer step executor around each agent invocation, not by
  the state machine itself (the state machine only knows the state
  *before* and *after* a step, not the retries inside it).
- *Retry with backoff*: same executor, wraps `LLMProvider.complete()`/
  `.stream()` calls; failures exhausted → the executor requests a
  `DEGRADED_PLAIN_RAG` or `FAILED` transition, which the state machine
  either allows or rejects per the adjacency table.
- *Graceful degradation to plain RAG*: modeled as a first-class terminal
  state (`DEGRADED_PLAIN_RAG`), not an exception path bolted on after the
  fact — a degraded run is still a fully valid, inspectable `Run` record.
- *Approval gate (approve/reject/edit-and-approve)*: `PENDING_APPROVAL →
  APPROVED|REJECTED` transitions, audited via the `Run`'s recorded steps
  (ADR-0006). "Edit-and-approve" is modeled as an edit event recorded as
  its own step immediately before the `APPROVED` transition, so the
  audit trail shows what the supervisor changed, not just that they
  approved.

## Consequences
- Adding a step later (e.g. a stretch-goal agent) means adding a state
  and adjacency entries, not rewriting a loop's control flow — cheap and
  explicit, at the cost of the adjacency table growing with workflow
  complexity. Acceptable: our workflow is fixed-size by the domain pack.
- The state machine enumerates *orchestration* state only. Each agent's
  internal reasoning (its own tool calls, its own retries within one
  step) is opaque to the state machine by design — that detail lives in
  the step's `RunStep` record (ADR-0006), not in `RunState`.
