# ADR-0003: LLM provider abstraction — OpenAI (hosted) with Ollama (local) fallback

## Status
Accepted

## Context
The brief mandates one interface covering completion, streaming, tool
calling and embeddings, with ≥2 working implementations — a hosted API and
an alternative/local model — selected by configuration with a documented
fallback chain, "so you never need to pay for anything."

Note: our assigned twist is **T4 (Audit & replay)**, not T2 (offline/
degraded mode) — we are not required to build automatic no-internet
detection with honestly-documented capability differences. We still need
the fallback chain because it is called out separately, under §4, as
mandatory for every variant regardless of twist.

## Decision
`LLMProvider` (`src/application/ports/llm_provider.py`) is the single port.
Two adapters implement it:

1. **`OpenAIProvider`** (primary, hosted) — chat completion, streaming, and
   tool calling via the Chat Completions / Responses API, and embeddings
   via `text-embedding-3-small`. Chosen as primary because it is the only
   mainstream vendor that natively covers all four capabilities the port
   requires from a single account, which keeps the primary adapter simple.
2. **`OllamaProvider`** (fallback, local) — a locally-run Ollama server
   (e.g. `llama3.1` or `qwen2.5` for completion/tool calling,
   `nomic-embed-text` for embeddings). Genuinely $0 and works with no
   internet and no signup, which is also why development and the unit/
   integration test tiers can run entirely against it without needing a
   hosted key at all.

**Fallback chain:** `LLM_PROVIDER` config selects the primary
(`openai` | `ollama`). On a primary-provider failure (auth error, rate
limit, timeout after retry-with-backoff — FR-5), the orchestrator falls
back to `LLM_FALLBACK_PROVIDER` (default `ollama`) for that call, and logs
which provider actually served each request against the run's correlation
ID (FR-9). Fallback is per-call, not sticky, so a transient primary outage
doesn't strand the whole run on the weaker local model.

## Alternatives considered
- **Anthropic Claude as primary** — excellent completion/tool-calling, but
  has no first-party embeddings API, which would force a third vendor into
  the "one interface" just for `embed()`. Rejected for this ADR's
  interface shape, though Claude remains a natural second hosted adapter
  to add later behind the same port if time allows.
- **LiteLLM / a routing SDK** instead of hand-rolled adapters — would give
  more providers for free, but the SDK's abstraction would leak into
  `application/`, violating ADR-0001's dependency rule. Rejected in favor
  of two adapters we fully control.

## Consequences
- `OllamaProvider` requires the developer/grader to have Ollama installed
  locally to exercise that path; documented in README's quick-start.
- Embedding dimensionality differs between `text-embedding-3-small` (1536)
  and `nomic-embed-text` (768) — the vector store schema must not hard-code
  a dimension; each collection/index is created per active embedding
  provider (see ADR-0004).
- Tool-calling argument schemas must be validated identically regardless
  of which provider produced them, before execution (OWASP LLM Top 10:
  insecure output handling) — this validation lives in the application
  layer, not in either adapter.
