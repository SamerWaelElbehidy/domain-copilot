# Business Requirements Document — Domain Copilot (D5T4)

| | |
|---|---|
| **Product** | Domain Copilot for industrial field maintenance |
| **Domain / twist** | D5 Industrial (field maintenance) / T4 Audit and replay |
| **Organisation (fictional)** | Dawlia Furniture Works, Damietta: seven machine types, one site |
| **Status** | Reflects the code on `main`. Section 9 says, requirement by requirement, what is implemented, partial or deferred |

## 1. Context

A furniture factory runs seven kinds of machine: a CNC router, a drying kiln, a laminating
press, a spray booth, an edge bander, a dust-extraction system and an air compressor. For each there are
manuals (some with a superseded older revision still in circulation), lockout-tagout cards
and service bulletins, plus facility-wide safety policies.

When something goes wrong, a technician spends time finding the right manual **and the right revision**, works
out the diagnostic steps, and must not skip a safety prerequisite. A supervisor then authorises the work.
The costly failures are not slow searches. They are (a) diagnosing from a superseded manual, (b) skipping or
mis-stating a safety step, and (c) work dispatched without anyone accountable having approved it.

The Copilot answers questions with citations to the exact manual passage, and runs a three-agent workflow that
turns a symptom into a **draft** work order. A human supervisor approves, rejects or edits it. Every run is recorded in
a tamper-evident log that can be replayed.

The risk the brief names for this domain is **skipping a safety prerequisite**. The design answer is that safety
prerequisites are enforced by code, not left to the model (BR-07).

## 2. Personas

| Persona | Goals | Pains | What the system gives them |
|---|---|---|---|
| **Field technician** | Fix a fault quickly and safely; know which steps and which precautions apply | Several manual revisions; scattered safety rules; no time to read 40 pages | Ask questions with cited answers; describe a fault and get a drafted work order with the full safety checklist |
| **Maintenance supervisor** | Approve only work that is correct and safe; be able to show why later | Reviewing drafts of unknown quality; no record of what the tool did | A queue of drafts to approve, reject or edit; the safety list cannot be shortened; a replayable audit trail |
| **Plant administrator** | Keep the knowledge base current and the tool's spend under control | Stale manuals; unknown usage and cost | Upload new manuals with visible ingestion status; per-user usage and cost |
| **Safety / compliance reviewer** *(secondary, read-only in practice)* | Prove afterwards that nothing was dispatched unapproved | Logs that could be edited | Hash-chained run log, replay that refuses a tampered log |

## 3. Objectives and measurable success criteria

Measured values come from [docs/EVALUATION.md](EVALUATION.md) (local `qwen2.5:3b`) or from tests. A criterion marked
**structural** is enforced by code and proven by a test, not sampled.

| ID | Objective | Success criterion | Result |
|---|---|---|---|
| OBJ-1 | Answers are grounded | Every answer cites source chunks; every cited chunk exists in the retrieved set | Structural, `tests/unit/agents/test_answerer.py` |
| OBJ-2 | The right passage is found | Retrieval hit-rate at top 5 on answerable golden questions is at least 90% | 100% |
| OBJ-3 | The copilot does not guess | 100% of out-of-corpus and ambiguous golden questions are refused | 100% (6 of 6) |
| OBJ-4 | Injection does not steer it | No forbidden output in any of 5 injection cases, 3 of them indirect | 5 of 5 resisted; 2 of them were actually answered rather than refused (see the evaluation, section 5) |
| OBJ-5 | No unapproved dispatch | Zero dispatches without a valid approval for that specific work order | Structural, `tests/contract/test_tool_registry.py`, `tests/unit/agents/test_orchestrator.py` |
| OBJ-6 | Safety steps are never skipped | Every drafted work order carries the complete safety checklist of the matched equipment's current manual | Structural, checklist copied by code; `tests/unit/agents/test_agents.py` |
| OBJ-7 | Runs are accountable | Any run can be inspected and replayed by id; editing a stored step is detected | Structural, `tests/integration/test_postgres_repositories.py` (real Postgres) and `tests/unit/agents/test_orchestrator.py` |
| OBJ-8 | Usable answers | Answer accuracy on answerable golden questions | 73% with the 3B model (55% with 1B). Below what a production system needs; see the gap table |
| OBJ-9 | Cost is visible | Every model call is recorded with user, run, tokens, cost | Structural, `tests/api/test_ask.py`, `tests/api/test_runs.py` |

## 4. Requirements

Each requirement has an id, an acceptance criterion, and the brief's requirement it satisfies (in brackets).
The traceability matrix in section 9 gives status and evidence.

**Knowledge base**

- **BR-01 Ingestion.** *(FR-1)* The admin can add PDF and Markdown documents. Stages are separable: extract, clean,
  chunk, embed, index. Metadata (equipment, revision, effective date, type, section, source reference) is kept. Re-ingesting a
  document does not duplicate chunks. Each document shows an ingestion status and, on failure, the reason.
  *Accept:* uploading a Markdown and a PDF each produce chunks; uploading the same file twice leaves the chunk count unchanged;
  a disguised or malformed file is rejected before anything is stored; an indexing failure is listed against the document.
- **BR-02 Structure-aware chunking.** *(FR-2)* Chunk boundaries follow the manual's structure. Each safety prerequisite and each
  diagnostic item is one chunk, never split. *Accept:* the seven safety steps of the router manual yield seven chunks; a
  wrapped safety step stays one chunk, including in PDF input.
- **BR-03 Hybrid retrieval, revision-aware.** *(FR-2)* Retrieval combines dense and keyword search with a documented fusion, and considers only
  current (non-superseded) documents, optionally scoped to one machine. *Accept:* a question about the router never returns text from the
  superseded Rev. B.
- **BR-04 Grounded answers and refusal.** *(FR-2, principle 1)* Every answer cites the passages it used. When evidence is weak, missing,
  unsupported by its own citations, or in conflict, the system refuses and says why. *Accept:* the evaluation's out-of-corpus,
  ambiguous and conflicting cases are refused or cite every conflicting source.

**Workflow**

- **BR-05 Symptom to work order.** *(D5)* A described fault is matched to a machine and its current manual revision, a diagnostic sequence is
  retrieved, safety prerequisites are attached, and a draft work order is produced. Three specialised agents with an
  orchestrator, each with an allow-listed tool set and typed input and output.
- **BR-06 Human approval.** *(principle 2, FR-5)* A supervisor can approve, reject or edit-and-approve, and nothing is dispatched before that.
  The person who raised a run cannot approve it. Approvals and edits are recorded.
- **BR-07 Safety prerequisites enforced by code.** *(D5 risk)* The safety checklist of the matched equipment is fetched
  completely and attached by code. A reviewer may add safety steps, never remove them. A work order without a safety checklist
  cannot be submitted, at the domain level and in the database.
- **BR-08 Controlled execution.** *(FR-5)* Per-step timeout, retry with backoff, an iteration limit on agent loops, and graceful degradation to a
  plain grounded answer when the workflow fails. A refusal is a legitimate end state.
- **BR-09 Real-time.** *(FR-6)* Answers stream token by token. Workflow progress is pushed as events. Cancelling a run stops the server-side work.

**Access, accountability, operations**

- **BR-10 Roles.** *(FR-8)* Technician, supervisor and administrator have different permissions, enforced on the server. A technician sees only their own
  runs and questions. An administrator can inspect everything but cannot approve dispatch.
- **BR-11 Audit and replay (twist T4).** Every run is persisted step by step in a hash-chained log. `replay <run-id>` plays back the recorded steps
  without calling a model. A log that was edited after the fact is detected and its replay is refused.
- **BR-12 Observability.** *(FR-9)* A correlation id links the request, the run and each model call. Tokens and cost are recorded per call and
  queryable per user and per run. Health and readiness endpoints exist.
- **BR-13 Surface.** *(FR-7)* A documented HTTP API (OpenAPI) and a minimal web UI covering ingest, ask with citations, run the workflow, act on
  the approval gate, view a trace; persistent session history.

**Engineering and security**

- **BR-14 Swappable providers.** *(Section 4 of the brief)* One interface covers completion, streaming, tool calls and embeddings, with at least two
  implementations (local and hosted), selected by configuration, with a documented fail-over chain.
- **BR-15 Clean architecture.** Domain and application layers depend on no LLM SDK, vector-store SDK or web framework, verified by a test.
- **BR-16 Security controls.** *(Section 5)* Controls for the OWASP Web and LLM Top 10 items listed in [SECURITY.md](SECURITY.md), including
  prompt-injection resistance (direct and indirect), PII redaction, tool allow-lists, unbounded-consumption limits, pinned and scanned dependencies.
- **BR-17 Evaluation.** *(FR-3)* A golden set of at least 25 questions with at least 5 adversarial cases, and a runnable harness reporting hit-rate,
  groundedness and refusal correctness, with the honest baseline recorded.
- **BR-18 Packaging.** One command starts everything including the databases and models and seeds demo data; complete `.env.example`.
- **BR-19 Engineering process.** Work through pull requests with CI (build, lint, tests, dependency and secret scanning); issues and milestones;
  an agentic-workflow record and an AI-usage log.

## 5. Explicitly out of scope

| Out of scope | Why |
|---|---|
| Arabic documents, cross-lingual queries, RTL | The assigned twist is T4. The user base was decided to be English-speaking for the first release. Deferred, [issue #23](https://github.com/SamerWaelElbehidy/domain-copilot/issues/23) |
| OCR of scanned PDFs | Scans are rejected with a clear error. [Issue #24](https://github.com/SamerWaelElbehidy/domain-copilot/issues/24) |
| Multi-tenancy, multi-site | One factory. Tenancy is twist T0, not ours |
| Single sign-on, MFA, self-service registration | Local accounts are enough to demonstrate role-based control; SSO belongs to the deployment environment |
| Integration with a real maintenance system (CMMS) | "Dispatch" records the approved work order and its state; it does not call an external system |
| Real personal or plant data | Synthetic corpus only, by the brief's rules |
| Automated machine control | The copilot advises and drafts. It never actuates equipment |
| Names and addresses in PII redaction | Needs an NER model. [Issue #22](https://github.com/SamerWaelElbehidy/domain-copilot/issues/22) |
| A production deployment | Optional in the brief. [Issue #26](https://github.com/SamerWaelElbehidy/domain-copilot/issues/26) |

## 6. Business rules

| ID | Rule | Enforced by |
|---|---|---|
| RULE-1 | No work order is dispatched without approval by a supervisor. | `WorkOrder.dispatch()`, `ToolRegistry` gate with an HMAC-signed token bound to one work order, orchestrator state machine |
| RULE-2 | The person who raised a run cannot approve it. | `POST /runs/{id}/decision` |
| RULE-3 | An administrator cannot approve dispatch. | `ROLE_PERMISSIONS` in `domain/value_objects/role.py` |
| RULE-4 | A reviewer may add safety steps but never remove them. | `CopilotOrchestrator._apply_edits` |
| RULE-5 | Superseded manual revisions are never used to answer or plan. | `scoped_search` restricts to current documents |
| RULE-6 | When evidence is missing, weak, unsupported or conflicting, refuse and say why. | `GroundedAnswerer` guards |
| RULE-7 | The safety checklist is taken from the manual by code, never from model output. | `get_safety_prerequisites` tool, `WorkOrderGenerator` |
| RULE-8 | The run log is append-only in the application and hash-chained; a broken chain blocks replay. | `Run.record_step`, `replay_run` |
| RULE-9 | Personal identifiers are removed before storage and before any model sees them. | `application/pii.py`, applied at the API boundary |
| RULE-10 | An approval token authorises exactly one work order. | `ApprovalAuthority` |

## 7. Assumptions

1. The corpus is synthetic, in English, and small (30 documents for seven machines). It is sized to demonstrate behaviour, not to be a real plant's library.
2. Supervisors are trusted to judge technical correctness. The system makes the safety list unremovable but does not verify that the diagnosis is right.
3. A small local model (3B parameters) is the default because it needs no key and no money. Its limits are measured, not hidden (OBJ-8).
4. One API replica. In-process rate limits and circuit breaker state are acceptable at this scale.
5. The database and model host are inside the organisation's control; a hosted model provider is an explicit, configurable exception.
6. Users' devices and browsers are managed by the organisation. Transport security (TLS) is terminated in front of the app in a real deployment.
7. "Dispatch" means recording an approved work order in the system. Handing it to a maintenance system is out of scope.
8. Reasonable ambiguity in the brief was resolved as follows: the "5-minute demo path" uses the bundled demo accounts; "at least one write tool" is
   `dispatch_work_order` (gated) plus `draft_work_order` (creates a draft only); a "hosted API" provider is any OpenAI-compatible endpoint.

## 8. Risks

| ID | Risk | Likelihood | Impact | Mitigation | Residual |
|---|---|---|---|---|---|
| RISK-1 | Small model gives an unsupported answer | High | Medium | Citation and support checks, relevance threshold, refusal, evaluation | Some correct answers are refused (23% false refusals measured) |
| RISK-2 | Poisoned or malicious document (indirect prompt injection) | Medium | High | Quoted-data prompt, injection scan and quarantine at retrieval, output guards, admin-only upload, 3 indirect cases in the evaluation | A novel phrasing could pass the scan; the output guards and approval gate are the backstop |
| RISK-3 | A superseded manual is used | Medium | High | Current-revision filter on every retrieval; revision cases in the evaluation | Depends on correct status metadata at upload |
| RISK-4 | Supervisor approves without reading | Medium | High | Checklist shown in full, cannot be shortened, decisions recorded and attributable | Human factors; outside software |
| RISK-5 | Abuse-driven token spend | Medium | Medium | Per-user rate limits, output token cap, input size caps, usage view | In-process limiter does not scale across replicas (issue #20) |
| RISK-6 | Hosted provider outage or exhausted free tier | High | Low | Local default, fail-over chain, circuit breaker | Different provider, different answer quality; labelled in the audit log |
| RISK-7 | Leaking personal data to a hosted model | Low | High | Redaction before any model call, local default, documented data flow | Names and addresses are not redacted (issue #22) |
| RISK-8 | Someone edits the audit log | Low | High | Hash chain, replay refuses a broken chain | Anyone with database write access can rewrite the whole chain consistently. Anchoring the head hash externally is the fix (gap table) |
| RISK-9 | Corpus too small to be convincing | Certain | Medium | Stated openly; 30 documents (the floor), about 11,000 words | The 150-page target is not met (gap table) |

## 9. Traceability matrix

Status: **implemented**, **partial**, **deferred**. Evidence is code, tests and documents in this repository.

| Requirement | Status | Evidence |
|---|---|---|
| BR-01 Ingestion | implemented | [`ingest_document.py`](../src/application/use_cases/ingest_document.py), [`ingestion/`](../src/application/use_cases/ingestion), [`upload_document.py`](../src/application/use_cases/upload_document.py); [`tests/api/test_documents.py`](../tests/api/test_documents.py), [`tests/unit/application/test_pdf_ingestion.py`](../tests/unit/application/test_pdf_ingestion.py) |
| BR-02 Chunking | implemented | [ADR-0002](adr/0002-chunking-retrieval-strategy.md), [`chunk_document.py`](../src/application/use_cases/ingestion/chunk_document.py), [`test_chunk_document.py`](../tests/unit/application/test_chunk_document.py) |
| BR-03 Retrieval | implemented | [ADR-0004](adr/0004-vector-store-and-hybrid-retrieval.md), [`hybrid_search.py`](../src/application/use_cases/hybrid_search.py), [`scoped_search.py`](../src/application/use_cases/scoped_search.py), [`test_hybrid_search.py`](../tests/unit/application/test_hybrid_search.py). The one justified enhancement is metadata filtering (equipment and current revision) |
| BR-04 Grounded answers, refusal | implemented | [`answer_question.py`](../src/application/use_cases/answer_question.py), [`grounding.py`](../src/application/use_cases/grounding.py), [`conflict_check.py`](../src/application/use_cases/conflict_check.py), [`test_answerer.py`](../tests/unit/agents/test_answerer.py), [EVALUATION.md](EVALUATION.md) |
| BR-05 Workflow, 3 agents | implemented | [`agents/`](../src/application/agents), [`orchestrator.py`](../src/application/use_cases/orchestrator.py), [`test_agents.py`](../tests/unit/agents/test_agents.py), [`test_orchestrator.py`](../tests/unit/agents/test_orchestrator.py). Five tools, typed contracts in [`contracts.py`](../src/application/agents/contracts.py) |
| BR-06 Approval gate | implemented | [`approval_authority.py`](../src/application/agents/approval_authority.py), [`tool_registry.py`](../src/application/agents/tool_registry.py), [`routes/runs.py`](../src/api/routes/runs.py), [`test_runs.py`](../tests/api/test_runs.py), [`test_tool_registry.py`](../tests/contract/test_tool_registry.py) |
| BR-07 Safety enforced by code | implemented | [`tool_catalog.py`](../src/application/agents/tool_catalog.py) (complete fetch, fails closed), [`work_order.py`](../src/domain/entities/work_order.py), migration `0003` CHECK, [`test_work_order.py`](../tests/unit/domain/test_work_order.py) |
| BR-08 Controlled execution | implemented | [`orchestrator.py`](../src/application/use_cases/orchestrator.py) (`StepPolicy`, `RETRYABLE`, `_degrade_or_fail`), [`tool_loop.py`](../src/application/agents/tool_loop.py) (max iterations), [ADR-0005](adr/0005-orchestration-pattern.md) |
| BR-09 Real-time | implemented | [`routes/ask.py`](../src/api/routes/ask.py) (SSE), [`run_manager.py`](../src/api/run_manager.py) (progress, cancel), [`test_ask.py`](../tests/api/test_ask.py), [`test_runs.py`](../tests/api/test_runs.py) |
| BR-10 Roles | implemented | [`role.py`](../src/domain/value_objects/role.py), [`deps.py`](../src/api/deps.py), [`test_auth_and_security.py`](../tests/api/test_auth_and_security.py), ownership tests in `test_runs.py` and `test_ask.py` |
| BR-11 Audit and replay | implemented | [ADR-0006](adr/0006-audit-and-replay.md), [`run_step.py`](../src/domain/value_objects/run_step.py), [`replay_run.py`](../src/application/use_cases/replay_run.py), [`scripts/replay.py`](../scripts/replay.py), tamper test in [`test_postgres_repositories.py`](../tests/integration/test_postgres_repositories.py). Partial on one point: the chain proves internal consistency, not that the head was not rewritten as a whole (gap table) |
| BR-12 Observability | implemented | [`correlation.py`](../src/application/correlation.py), [`llm_recording.py`](../src/application/llm_recording.py), [`routes/health.py`](../src/api/routes/health.py), `/usage`, `/runs/{id}/trace`. A custom trace store, which the brief accepts; OpenTelemetry export is deferred ([#25](https://github.com/SamerWaelElbehidy/domain-copilot/issues/25)) |
| BR-13 Surface | implemented | OpenAPI at `/docs`; [`src/api/static/`](../src/api/static); [`test_ui.py`](../tests/api/test_ui.py); session history in [`routes/sessions.py`](../src/api/routes/sessions.py). The UI was checked with a syntax check and API tests; it has not been exercised visually in a browser by the author |
| BR-14 Providers | implemented | [ADR-0003](adr/0003-provider-abstraction.md), [ADR-0007](adr/0007-provider-fallback-chain.md), [`ollama_provider.py`](../src/infrastructure/llm/ollama_provider.py), [`openai_compatible_provider.py`](../src/infrastructure/llm/openai_compatible_provider.py), [`llm_fallback.py`](../src/application/llm_fallback.py), [`test_llm_adapters.py`](../tests/contract/test_llm_adapters.py) |
| BR-15 Clean architecture | implemented | [ADR-0001](adr/0001-clean-architecture.md), [`test_architecture.py`](../tests/unit/test_architecture.py) |
| BR-16 Security | implemented, with gaps | [SECURITY.md](SECURITY.md) maps every control to its threat and lists what is not covered |
| BR-17 Evaluation | implemented | [`eval/golden_set.json`](../eval/golden_set.json) (35 cases, 13 adversarial), [`scripts/evaluate.py`](../scripts/evaluate.py), [EVALUATION.md](EVALUATION.md) with the failures |
| BR-18 Packaging | implemented | [`Dockerfile`](../Dockerfile), [`docker-compose.yml`](../docker-compose.yml), [`scripts/bootstrap.py`](../scripts/bootstrap.py), [`.env.example`](../.env.example); CI builds the image |
| BR-19 Process | implemented | Pull requests with CI, issues and milestones, [AGENTIC-WORKFLOW.md](AGENTIC-WORKFLOW.md), [AI-USAGE-LOG.md](AI-USAGE-LOG.md) |
| Arabic support | deferred | Out of scope, section 5 |
| OCR | deferred | Out of scope, section 5 |
| Corpus of 150+ pages | partial | 30 documents, about 11,000 words. The document-count floor is met; the page target is not. See the system design gap table |
