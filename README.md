# Domain Copilot — D5T4 (Industrial Field Maintenance × Audit & Replay)

> Status: 🚧 early scaffold — this README grows as the system is built. It is
> not yet the "assume Docker + 15 minutes" quick-start the final submission
> requires.

## Assigned variant

This repository targets **Domain Pack D5 (Industrial — field maintenance)**
with **Mandatory Twist T4 (Audit & replay)**, derived from the candidate's
National ID as instructed by the brief:

- `Domain = (last two digits of National ID) mod 7 = 5` → **D5**
- `Twist  = (sum of all digits of National ID) mod 8 = 4` → **T4**

(Only the derived remainders are recorded here, not the National ID itself —
this is a public repository.)

## What this system does (target scope)

A Copilot for industrial field-maintenance technicians at a fictional
furniture manufacturer. A technician describes an equipment symptom; the
system identifies the equipment and the correct manual revision, retrieves a
diagnostic sequence and its safety prerequisites (structurally enforced, not
left to the model to remember), and drafts a work order that a supervisor
must approve before dispatch. Every run can be replayed step-by-step from its
run ID.

See [`docs/BRD.md`](docs/BRD.md) (coming next) for personas, scope, and
acceptance criteria, and [`docs/SYSTEM-DESIGN.md`](docs/SYSTEM-DESIGN.md) for
the full architecture including what is deliberately deferred.

## Architecture

Clean Architecture (ports & adapters) — see
[`docs/adr/0001-clean-architecture.md`](docs/adr/0001-clean-architecture.md).

```
src/
  domain/          pure business logic, zero third-party deps
  application/     use cases, agent contracts, ports (interfaces)
  infrastructure/  adapters: LLM providers, vector store, persistence, OCR
  api/             FastAPI routers, DI wiring
```

## Stack

- Python 3.11+, FastAPI
- LLM: provider-abstracted (hosted API + local/free fallback — see ADR, TBD)
- Vector store: TBD (documented via ADR before ingestion is built)
- Relational store: TBD
- Docker Compose for local orchestration

## Status of required deliverables

This table is updated as the project progresses (12-day window).

| Deliverable | Status |
|---|---|
| Ingestion (FR-1) | not started |
| Retrieval (FR-2) | not started |
| Evaluation harness (FR-3) | not started |
| Multi-agent (FR-4) | not started |
| Orchestration (FR-5) | not started |
| Real-time streaming (FR-6) | not started |
| API + minimal UI (FR-7) | not started |
| Access control (FR-8) | not started |
| Observability (FR-9) | not started |
| BRD / System Design / Architecture docs | not started |
| Security & Evaluation reports | not started |
| Teaching pack + videos | not started |

## AI-assisted development

This project is built with heavy, deliberate AI assistance (Claude), as
explicitly permitted and expected by the brief. See
[`docs/AI-USAGE-LOG.md`](docs/AI-USAGE-LOG.md) (coming next) for what was
delegated, what was written by hand, and where the AI needed correcting, and
[`docs/AGENTIC-WORKFLOW.md`](docs/AGENTIC-WORKFLOW.md) for the configured
agentic coding workflow itself.
