# ADR-0004: Qdrant + Postgres full-text search, fused with Reciprocal Rank Fusion

## Status
Accepted

## Context
FR-2 requires hybrid retrieval (dense + keyword) with a documented fusion
method, plus one justified enhancement (we are using metadata filtering —
see ADR-0002's `section_type` filtering for safety-prerequisite
completeness). We also need a relational store for equipment/document
metadata, work orders, and T4's audit/replay log regardless of vector
store choice, so that store is a fixed cost, not an extra one.

## Decision
- **Dense vector search: Qdrant**, self-hosted via `docker compose`.
  Chosen over ChromaDB and pgvector because its payload-filtering DSL is
  the most mature of the three for our access pattern: every retrieval
  call filters by `equipment_id`, `manual_revision`, and often
  `section_type` before or alongside the similarity search, not after.
- **Keyword search: PostgreSQL full-text search** (`tsvector` + `ts_rank`)
  on the same Postgres instance already required for relational metadata.
  Rejected a dedicated engine (e.g. Elasticsearch, Meilisearch): it would
  be a third moving part in `docker compose up` for a corpus of 30-some
  documents, where Postgres FTS is more than adequate and keeps ops
  simple — directly serving the brief's "plain and functional" instinct.
- **Fusion method: Reciprocal Rank Fusion (RRF).** For each chunk, score
  = Σ 1 / (k + rank_i) over each ranker it appears in (k = 60, a standard
  default). RRF is chosen over a weighted linear blend of raw scores
  because cosine similarity (Qdrant) and `ts_rank` (Postgres) are on
  incomparable scales — RRF only needs each ranker's *rank order*, not a
  normalized score, which removes an entire class of tuning bugs where
  one ranker silently dominates because its raw scores happen to run
  higher.

Both `VectorStore` and `KeywordSearchIndex` adapters return the same
`ScoredChunk` shape; the fusion step lives in the application layer
(`application/use_cases/`), not in either adapter, so it is unit-testable
against fake rankers with no real Qdrant/Postgres running.

## Alternatives considered
- **ChromaDB** — simpler local dev story (embedded, no server), but
  weaker metadata filtering and no first-class production deployment
  story; rejected once filtering became load-bearing for safety-chunk
  completeness, not just a nice-to-have.
- **pgvector only (no separate vector DB)** — would collapse to one
  engine total. Rejected: pgvector's filtered-ANN performance and payload
  indexing are less mature than Qdrant's at the metadata-filter-heavy
  pattern this domain needs, and splitting vector/keyword across two
  engines still keeps `docker compose up` to two services, not three.

## Consequences
- Two schemas to migrate: Qdrant collection (recreated if the embedding
  dimension changes — see ADR-0003) and Postgres tables/migrations for
  metadata, FTS index, work orders, and the T4 audit/replay log.
- RRF's `k` constant is a tunable we will report on in `docs/EVALUATION.md`
  once the golden set (FR-3) can measure hit-rate sensitivity to it.
