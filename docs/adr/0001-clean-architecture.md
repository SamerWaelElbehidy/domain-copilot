# ADR-0001: Use Clean Architecture with ports & adapters

## Status
Accepted

## Context
The brief requires that the domain and application layers never depend on any
LLM SDK, vector-store SDK, or web framework, and that swapping the LLM
provider, embedding model, or vector store requires configuration plus one
adapter — not a change to business logic. We also need to support ≥2 LLM
provider implementations (a hosted API and a local/alternative model) behind
one interface, per the mandatory provider-abstraction requirement.

## Decision
We use **Clean Architecture** (a ports & adapters style), split into four
layers under `src/`:

- `domain/` — entities, value objects, domain errors. Pure Python, zero
  third-party dependencies. This is the only layer that must never change
  when we swap a provider.
- `application/` — use cases (e.g. "answer question with citations", "run
  maintenance workflow"), agent role definitions, and **ports**: abstract
  interfaces such as `LLMProvider`, `EmbeddingProvider`, `VectorStore`,
  `DocumentRepository`. Depends only on `domain/`.
- `infrastructure/` — adapters that implement the ports: concrete OpenAI /
  Anthropic / local-model clients, a Qdrant or pgvector adapter, a
  SQL repository. Depends on `application/` (to implement its interfaces)
  and on whichever third-party SDK it wraps.
- `api/` — FastAPI routers, request/response schemas, dependency-injection
  wiring. The only layer allowed to know about HTTP.

## Why Clean Architecture over Hexagonal/Onion/Vertical Slice
Hexagonal and Onion are close cousins of the same idea (ports & adapters);
we name it Clean Architecture because the four-layer split above maps
directly onto Uncle Bob's dependency rule, which is the easiest version of
this idea to teach in a 90-minute session — and this repository doubles as
a teaching artifact. Vertical Slice was rejected: this project has few,
deep, shared concerns (one retrieval pipeline, one agent contract format,
one audit/replay mechanism reused by every workflow step), which favors a
shared kernel over per-feature slices.

## Consequences
- Every port gets at least two adapters before this repo is "done":
  one hosted-API implementation and one free/local implementation, selected
  by configuration (see ADR to follow on provider fallback chain).
- Unit tests for `domain/` and `application/` stub every port — no real
  LLM or DB calls in that test tier.
- Slightly more ceremony for small features (an interface plus an adapter
  instead of a direct SDK call). Accepted deliberately: the acceptance test
  in the brief ("swap a provider with config + one adapter") is the whole
  point of this ADR.
