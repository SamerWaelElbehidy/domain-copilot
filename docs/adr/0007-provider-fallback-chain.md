# ADR-0007: Ordered provider chain with a circuit breaker; embeddings never fail over

## Status
Accepted

## Context
FR-4 requires at least two `LLMProvider` implementations and graceful
degradation when the preferred one fails. ADR-0003 gave us the port. Two
questions remained: how failover behaves, and what happens to embeddings.

Failure modes we have to survive: the local Ollama server is down or
cold-starting (timeouts were our most common real failure in development),
a hosted host rate-limits us (429), a key is revoked (401), or a host has
an outage (5xx).

## Decision
1. **Two adapters.** `OllamaProvider` (local, free, the default) and
   `OpenAICompatibleProvider` (hosted). The second speaks the
   chat-completions protocol that OpenAI and many free-tier hosts share, so
   choosing another host is `OPENAI_BASE_URL` plus a key, not new code.
2. **One error vocabulary.** Adapters translate transport and HTTP failures
   into `ProviderUnavailableError` (down, timeout, 429, 5xx, 401/403) or
   `ProviderRejectedError` (any other 4xx: the request itself is bad and
   another provider would refuse it too). `ProviderUnavailableError` subclasses
   `ConnectionError`, so the orchestrator's existing retry-with-backoff treats
   it as retryable. Before this, an httpx error was a plain `Exception` and
   failed a run on the first blip.
3. **`FallbackLLMProvider`** implements the port and tries providers in
   `LLM_PROVIDER_CHAIN` order. It fails over on unavailable, not on rejected.
4. **Circuit breaker.** After `LLM_FAILURE_THRESHOLD` consecutive failures a
   provider is skipped for `LLM_COOLDOWN_SECONDS`. Without it, a dead host
   costs a full timeout on every request. If every breaker is open we try
   all of them anyway rather than refuse to try.
5. **Streaming fails over only before the first event.** Tokens already sent
   to the client cannot be taken back, and splicing one model's continuation
   onto another's half-sentence would produce an answer nobody wrote. A
   mid-stream failure is raised.
6. **Embeddings never fail over.** Two embedding models produce vectors in
   different spaces. A fallback would not error; it would quietly return
   nonsense neighbours. The embedding provider is fixed by
   `EMBEDDING_PROVIDER` and its outage is an outage. Chat can degrade;
   retrieval cannot be allowed to.
7. **Accounting per attempt.** Each provider is wrapped in its own recorder,
   so a failed attempt is recorded as an error under the provider that
   failed, and the run's audit log names the provider that actually served
   each step (`provider_used`).
8. **Secrets.** The API key lives only in an environment variable and the
   Authorization header. Errors carry the provider name and status code, never
   headers, URL or body; the adapter's `repr` omits the key. A missing key with
   `openai` in the chain fails at startup.

## Consequences
- Local-only remains the default and needs no key, so CI and a reviewer's
  first run cost nothing.
- Failing over mid-agent-loop hands one provider's tool-call history to the
  other; the hosted adapter mints tool-call ids for calls that had none.
- Different models answer differently, and the evaluation numbers are for the
  local model. A run served by the fallback is labelled as such in its audit
  log, so its quality is not silently attributed to the primary.
- Failover state lives in process memory. With several API replicas each has
  its own breaker; acceptable for this scale, and noted in the design doc.

## Alternatives considered
- **Retry only, no chain.** Cannot help when the provider is down for minutes.
- **Fail over embeddings by re-embedding the corpus on the fly.** Correct but
  slow and expensive for a request path; a re-index is an operator decision.
- **A gateway service (LiteLLM and similar).** Solves this, adds a moving part
  and hides the failure semantics we wanted to show and test ourselves.
