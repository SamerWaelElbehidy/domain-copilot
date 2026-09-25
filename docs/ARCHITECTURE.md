# Architecture

All diagrams are [Mermaid](https://mermaid.js.org) **source in this file**, so
they render on GitHub, diff in pull requests, and can be edited as text. Nothing
here is an exported image.

Contents: [1. C4 level 1](#1-c4-level-1--system-context) ·
[2. C4 level 2](#2-c4-level-2--containers) ·
[3. C4 level 3](#3-c4-level-3--components-of-the-api-container) ·
[4. Sequence: the agentic workflow](#4-sequence-the-agentic-workflow-with-the-approval-gate) ·
[5. Sequence: streaming a grounded answer](#5-sequence-a-streamed-grounded-answer) ·
[6. Data flow and trust boundaries](#6-data-flow-trust-boundaries-and-what-the-llm-provider-sees) ·
[7. ER diagram](#7-er-diagram) · [8. Layer dependencies](#8-layer-dependency-diagram) ·
[9. Run state machine](#9-run-state-machine) · [10. ADR index](#10-architecture-decision-records)

The variant is **D5 (industrial field maintenance) with twist T4 (audit and replay)**.
The business is a fictional furniture factory, *Dawlia Furniture Works*, in
Damietta. All documents are synthetic.

---

## 1. C4 level 1 — system context

Who uses the system and what it depends on.

```mermaid
flowchart TB
    tech["<b>Maintenance technician</b><br/>[Person]<br/>Describes a fault, asks<br/>questions, raises work orders"]
    sup["<b>Maintenance supervisor</b><br/>[Person]<br/>Approves, rejects or edits<br/>work orders; replays runs"]
    adm["<b>Administrator</b><br/>[Person]<br/>Uploads manuals, watches<br/>usage and ingestion status"]

    copilot["<b>Domain Copilot</b><br/>[Software system]<br/>Grounded Q&A with citations and a<br/>multi-agent work-order workflow with<br/>a human approval gate and an audit log"]

    llm["<b>LLM provider chain</b><br/>[External / local system]<br/>Local Ollama by default;<br/>optional hosted OpenAI-compatible API"]

    tech -->|"asks, starts runs [HTTPS]"| copilot
    sup -->|"approves, replays [HTTPS]"| copilot
    adm -->|"uploads documents [HTTPS]"| copilot
    copilot -->|"chat, tools, embeddings [HTTP]"| llm
```

## 2. C4 level 2 — containers

What runs, what it stores, and how the pieces talk. Everything except the
optional hosted provider starts with `docker compose up`.

```mermaid
flowchart TB
    user["Browser<br/>[Person's device]"]

    subgraph compose["docker compose"]
        app["<b>API + UI</b><br/>[FastAPI, Python 3.11]<br/>REST, SSE, static web UI,<br/>orchestrator, agents"]
        pg[("<b>PostgreSQL 16</b><br/>users, runs, run_steps,<br/>work_orders, documents,<br/>chunks_fts, llm_calls,<br/>chat_sessions")]
        qd[("<b>Qdrant</b><br/>chunk embeddings<br/>(dense retrieval)")]
        ol["<b>Ollama</b><br/>chat model + embedding model"]
    end

    hosted["<b>Hosted LLM API</b><br/>[optional, OpenAI protocol]"]

    user -->|"HTTPS: JSON, SSE"| app
    app -->|"SQL (asyncpg)"| pg
    app -->|"HTTP (qdrant-client)"| qd
    app -->|"HTTP"| ol
    app -.->|"HTTPS, only if configured<br/>in LLM_PROVIDER_CHAIN"| hosted
```

Postgres holds both relational data and the **keyword side of hybrid search**
(`chunks_fts`, a generated `tsvector` with a GIN index). Qdrant holds the vectors.
Both are keyed by the same `chunk_id`, which is what lets rank fusion join them
([ADR-0004](adr/0004-vector-store-and-hybrid-retrieval.md)).

## 3. C4 level 3 — components of the API container

```mermaid
flowchart TB
    subgraph api["api/ (HTTP only)"]
        mw["Middleware<br/>correlation id, security headers,<br/>body limit, rate limit, error boundary"]
        routes["Routes<br/>auth, ask, sessions, runs,<br/>documents, health"]
        deps["deps.py<br/>authenticate + require(permission)"]
        rm["RunManager<br/>background tasks, SSE fan-out, cancel"]
        main["main.py<br/>composition root"]
    end

    subgraph app["application/ (use cases + ports)"]
        orch["CopilotOrchestrator<br/>state machine, retry, timeout,<br/>degrade, audit"]
        agents["Agents<br/>SymptomMatcher<br/>DiagnosticSafetyPlanner<br/>WorkOrderGenerator"]
        reg["ToolRegistry<br/>allow-lists, schema validation,<br/>approval gate"]
        ans["GroundedAnswerer<br/>retrieve, generate, validate"]
        srch["hybrid_search / scoped_search<br/>RRF fusion, current-revision filter,<br/>injection quarantine"]
        ing["upload_document + ingestion stages<br/>extract, clean, chunk, embed, index"]
        chain["FallbackLLMProvider<br/>RecordingLLMProvider"]
        ports["Ports<br/>LLMProvider, VectorStore, KeywordSearchIndex,<br/>Document/Run/WorkOrder/User/... repositories"]
    end

    subgraph dom["domain/ (pure Python)"]
        ent["Entities<br/>Run, WorkOrder, User, Chunk, ..."]
        vo["Value objects<br/>RunStep (hash chain), ApprovalToken,<br/>Role/Permission, Citation"]
        err["Domain errors"]
    end

    subgraph infra["infrastructure/ (adapters)"]
        ollama["OllamaProvider"]
        oai["OpenAICompatibleProvider"]
        pgrepo["Postgres repositories"]
        qdr["QdrantVectorStore"]
        sec["JWT, scrypt"]
        pdf["PypdfTextExtractor"]
    end

    mw --> routes --> deps
    routes --> rm --> orch
    routes --> ans
    routes --> ing
    orch --> agents --> reg
    reg --> srch
    ans --> srch
    agents --> chain
    ans --> chain
    srch --> ports
    ing --> ports
    chain --> ports
    orch --> ent
    ports --> ent
    ollama -.implements.-> ports
    oai -.implements.-> ports
    pgrepo -.implements.-> ports
    qdr -.implements.-> ports
    sec -.implements.-> ports
    pdf -.implements.-> ports
    main -.wires.-> infra
```

## 4. Sequence: the agentic workflow with the approval gate

`POST /runs` returns immediately; the workflow runs as a background task and
reports progress over SSE. Nothing is dispatched until a *different* human, a
supervisor, approves.

```mermaid
sequenceDiagram
    autonumber
    actor T as Technician
    actor S as Supervisor
    participant API as API (routes)
    participant RM as RunManager
    participant O as Orchestrator
    participant A as Agents (3)
    participant TR as ToolRegistry
    participant L as LLM chain
    participant DB as Postgres (runs, run_steps)

    T->>API: POST /runs {symptom}
    API->>API: authz (START_RUN), rate limit, strip control chars, redact PII
    API->>RM: submit(symptom, user)
    RM->>O: begin(created_by) -> run id
    O->>DB: save run (RECEIVED)
    API-->>T: 202 {run_id}
    T->>API: GET /runs/{id}/events (SSE)
    RM-->>T: step_started / step_finished ...

    par background task (correlation id + usage context copied from the request)
        RM->>O: execute(run, symptom)
        O->>DB: step "receive" (hash-chained)
        O->>A: 1. SymptomMatcher (timeout, retry with backoff)
        A->>L: complete(messages, tools)
        A->>TR: search_manual_chunks (allow-listed, schema-validated)
        TR-->>A: current-revision chunks only, injection-like chunks withheld
        A-->>O: typed EquipmentMatch
        O->>DB: step "match_symptom"
        O->>A: 2. DiagnosticSafetyPlanner
        A->>TR: get_safety_prerequisites (complete fetch, fails closed if truncated)
        A-->>O: typed DiagnosticPlan (safety list copied by code, not model output)
        O->>DB: step "diagnose"
        O->>A: 3. WorkOrderGenerator
        A->>TR: draft_work_order (side effect, ungated: creates a DRAFT only)
        A-->>O: typed WorkOrder draft
        O->>DB: step "draft_work_order"
        O->>DB: state PENDING_APPROVAL, step "await_approval"
        RM-->>T: awaiting_approval, stream_end
    end

    S->>API: GET /approvals
    API-->>S: queue with drafted work orders
    S->>API: POST /runs/{id}/decision {approve | reject | edit_and_approve}
    API->>API: authz (DECIDE), not the requester, redact comment
    API->>O: decide(run, reviewer, decision, edits)
    O->>DB: step "human_decision" (+ "reviewer_edit"); edits may add safety steps, never remove
    O->>TR: dispatch_work_order + HMAC ApprovalToken bound to this work order
    TR->>TR: verify signature, work order id, then execute
    O->>DB: step "dispatch", state DISPATCHED
    API-->>S: 200 dispatched

    Note over T,DB: Cancel: POST /runs/{id}/cancel cancels the asyncio task, the in-flight model call is abandoned, the run is closed as FAILED ("cancelled by client") and the log still verifies.
    Note over S,DB: Replay: GET /runs/{id}/replay verifies the hash chain first, then plays back stored steps. It never calls a model or a tool.
```

If a step fails after its retries the orchestrator degrades to a plain grounded
answer (`DEGRADED_PLAIN_RAG`); if evidence is missing or a safety prerequisite
cannot be established it ends in `REFUSED_LOW_EVIDENCE`. Both are recorded as steps.

## 5. Sequence: a streamed grounded answer

```mermaid
sequenceDiagram
    autonumber
    actor U as User
    participant API as POST /ask/stream
    participant G as GroundedAnswerer
    participant S as scoped_search
    participant L as LLM chain (stream)
    participant DB as Postgres

    U->>API: question (+ optional equipment, session)
    API->>API: authz (ASK), per-user rate limit, session ownership (404 if not yours), redact PII
    API-->>U: event: session
    API->>G: answer_stream(question, equipment)
    G->>S: embed query, dense + keyword, RRF fusion, current documents only
    S-->>G: numbered excerpts (+ count of quarantined chunks)
    alt below relevance threshold or no evidence
        G-->>API: answer {status: refused, reason}
    else enough evidence
        API-->>U: event: retrieval (which excerpts)
        G->>L: stream(system prompt v3 + excerpts + question)
        L-->>U: event: token ... (provisional, not yet validated)
        G->>G: validate: JSON shape, citations map to real excerpts,<br/>support score, injection scan, conflict guard
        G-->>API: answer {status: answered | refused}
    end
    API->>DB: store assistant message (+ citations, reason)
    API-->>U: event: answer (the only validated result)
    Note over U,L: If the client disconnects, the generator is cancelled, the provider stream is closed, and the model stops generating.
```

## 6. Data flow, trust boundaries, and what the LLM provider sees

```mermaid
flowchart LR
    subgraph untrusted["Untrusted (outside our control)"]
        user["User input<br/>(questions, symptoms, comments)"]
        upload["Uploaded documents<br/>(PDF / Markdown)"]
        modelout["Model output"]
    end

    subgraph tb1["Trust boundary 1: the API"]
        val["Validate + authz + rate limit<br/>strip control chars<br/>redact PII"]
    end

    subgraph inside["Trusted processing (our infrastructure)"]
        ingest["Ingestion<br/>type from bytes, size cap,<br/>metadata validated"]
        store[("Postgres + Qdrant")]
        retr["Retrieval<br/>current revisions only<br/>injection-like chunks withheld"]
        guard["Output guards<br/>schema, citations, support,<br/>conflicts, tool allow-lists,<br/>approval gate"]
        audit[("Hash-chained audit log")]
    end

    subgraph tb2["Trust boundary 2: the model provider"]
        llm["LLM provider<br/>local Ollama, or hosted if configured"]
    end

    user --> val --> retr
    upload --> ingest --> store
    store --> retr
    retr -->|"redacted question<br/>+ retrieved excerpts<br/>(as quoted data)"| llm
    ingest -->|"chunk text<br/>(embeddings only)"| llm
    llm --> modelout --> guard --> audit
    val --> audit
```

**What crosses boundary 2.** With the default `LLM_PROVIDER_CHAIN=ollama`,
nothing leaves the machine. If a hosted provider is added to the chain:

| Sent to the provider | Never sent |
|---|---|
| The **redacted** question or symptom | User names, ids, roles, tokens |
| The system prompt (versioned file) | The database, other users' data, other sessions |
| Retrieved manual excerpts (the model needs them) | Approval decisions, reviewer comments |
| Tool results the agent requested (manual chunks, draft fields) | Secrets, the API key of any *other* provider |
| Chunk text at ingestion, for embeddings (only if the embedding provider is hosted; the default is local) | Run ids, correlation ids |

**Privilege separation.** Retrieved text is wrapped as quoted, numbered data
and any chunk resembling an instruction to an AI is withheld before it reaches the
prompt (`scoped_search`, `injection_scan`). The model never produces the safety
checklist or the approval; both are produced by code.

## 7. ER diagram

```mermaid
erDiagram
    equipment ||--o{ manual_documents : "has"
    manual_documents ||--o{ chunks_fts : "is split into"
    equipment ||--o{ chunks_fts : "scopes"
    equipment ||--o{ work_orders : "for"
    equipment ||--o{ runs : "matched to"
    users ||--o{ runs : "created_by"
    runs ||--|{ run_steps : "hash-chained log"
    users ||--o{ chat_sessions : "owns"
    chat_sessions ||--o{ chat_messages : "contains"
    users ||--o{ llm_calls : "attributed to"
    runs ||--o{ llm_calls : "caused"

    equipment {
        text equipment_id PK
        text name
        text model_number
        text category
    }
    manual_documents {
        text document_id PK
        text equipment_id FK
        text revision
        date effective_date
        text doc_type "manual|loto|bulletin|policy"
        text status "current|superseded"
        text ingestion_status "pending|ingested|failed"
        text ingestion_error
    }
    chunks_fts {
        text chunk_id PK "same id as the Qdrant point"
        text document_id FK
        text equipment_id FK
        text section_type
        text content
        tsvector search_vector "generated, GIN"
    }
    work_orders {
        text work_order_id PK
        text equipment_id FK
        jsonb diagnostic_steps
        jsonb safety_checklist "CHECK non-empty once submitted"
        jsonb citations
        text status "draft|pending_approval|approved|rejected|dispatched"
        text approved_by
    }
    runs {
        text run_id PK
        text equipment_id FK
        text created_by FK
        text state "11-state machine"
        timestamptz started_at
    }
    run_steps {
        text run_id PK,FK
        int step_index PK
        text name
        text agent_name
        text provider_used
        jsonb input_snapshot
        jsonb output_snapshot
        text step_hash "chains to the previous step"
    }
    users {
        text user_id PK
        text username UK
        text role "technician|supervisor|admin"
        text password_hash "scrypt"
        boolean disabled
    }
    llm_calls {
        bigint call_id PK
        text correlation_id
        text user_id FK
        text run_id FK
        text provider
        text model
        int input_tokens
        int output_tokens
        numeric cost_usd
        text status "ok|error|cancelled"
    }
    chat_sessions {
        text session_id PK
        text user_id FK
        text title
    }
    chat_messages {
        bigint message_id PK
        text session_id FK
        text role
        text content
        text status "answered|refused"
        jsonb citations
    }
```

The vector store (Qdrant) is not in the ER diagram: it stores one point per chunk,
with the same `chunk_id` and the metadata fields used for filtering.

## 8. Layer dependency diagram

Arrows point from the depending layer to the layer it depends on. There is no
arrow from an inner layer to an outer one, and
[`tests/unit/test_architecture.py`](../tests/unit/test_architecture.py) fails the
build if one appears.

```mermaid
flowchart TB
    api["<b>api</b><br/>FastAPI routes, middleware, UI,<br/>composition root (main.py)"]
    infra["<b>infrastructure</b><br/>Ollama, OpenAI-compatible, Qdrant,<br/>Postgres, JWT, pypdf adapters"]
    app["<b>application</b><br/>use cases, agents, orchestrator,<br/>ports (interfaces)"]
    dom["<b>domain</b><br/>entities, value objects, domain errors<br/>(standard library only)"]

    api --> app
    api --> infra
    infra --> app
    app --> dom
    infra --> dom
    api --> dom
```

**How to verify the brief's swap test.** Adding a provider means one new file in
`infrastructure/llm/` implementing `LLMProvider`, one branch in
`infrastructure/llm/factory.py`, and an entry in `LLM_PROVIDER_CHAIN`. This was done
for real: the OpenAI-compatible adapter and the fallback chain were added after the
agents and orchestrator existed, and that change touched nothing in `domain/`. It did touch a small amount
of application plumbing (a `provider` field on `CompletionResult`, carried into the audit log's
`provider_used`), which is the honest measure of "configuration plus one adapter": the
business logic did not change, but observability had to learn which provider served a call.
Vector-store and embedding-model swaps follow the same
shape (`VectorStore` port; `EMBEDDING_PROVIDER` plus `OLLAMA_EMBED_MODEL`, with a
re-index and a recalibrated `RELEVANCE_THRESHOLD`, see `docs/EVALUATION.md`).

## 9. Run state machine

```mermaid
stateDiagram-v2
    [*] --> RECEIVED
    RECEIVED --> MATCHING_SYMPTOM
    MATCHING_SYMPTOM --> DIAGNOSING
    DIAGNOSING --> DRAFTING_WORK_ORDER
    DRAFTING_WORK_ORDER --> PENDING_APPROVAL
    PENDING_APPROVAL --> APPROVED: supervisor approve / edit_and_approve
    PENDING_APPROVAL --> REJECTED: supervisor reject
    APPROVED --> DISPATCHED: dispatch tool with signed token
    MATCHING_SYMPTOM --> REFUSED_LOW_EVIDENCE
    DIAGNOSING --> REFUSED_LOW_EVIDENCE
    MATCHING_SYMPTOM --> DEGRADED_PLAIN_RAG: retries exhausted
    DIAGNOSING --> DEGRADED_PLAIN_RAG: retries exhausted
    MATCHING_SYMPTOM --> FAILED
    DIAGNOSING --> FAILED
    DRAFTING_WORK_ORDER --> FAILED
    REJECTED --> [*]
    DISPATCHED --> [*]
    REFUSED_LOW_EVIDENCE --> [*]
    DEGRADED_PLAIN_RAG --> [*]
    FAILED --> [*]
```

## 10. Architecture decision records

| ADR | Decision |
|---|---|
| [0001](adr/0001-clean-architecture.md) | Clean Architecture with ports and adapters |
| [0002](adr/0002-chunking-retrieval-strategy.md) | Structure-aware chunking; safety steps are atomic chunks |
| [0003](adr/0003-provider-abstraction.md) | One `LLMProvider` port for completion, streaming, tools and embeddings |
| [0004](adr/0004-vector-store-and-hybrid-retrieval.md) | Qdrant + Postgres full-text, fused with Reciprocal Rank Fusion |
| [0005](adr/0005-orchestration-pattern.md) | State-machine orchestration |
| [0006](adr/0006-audit-and-replay.md) | Replay from persisted state; hash-chained steps (the T4 decision) |
| [0007](adr/0007-provider-fallback-chain.md) | Ordered provider chain with a circuit breaker; embeddings never fail over |
