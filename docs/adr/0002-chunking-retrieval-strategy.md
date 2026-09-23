# ADR-0002: Structure-aware chunking, split by section type

## Status
Accepted

## Context
FR-2 requires the chunking strategy to be a deliberate decision justified
against our document structure, not a default. Our corpus (D5, industrial
field maintenance) consists of equipment manuals with a consistent section
structure:

1. Overview & Specifications
2. Safety Prerequisites (numbered, atomic instructions)
3. Installation & Setup
4. Operating Procedures
5. Maintenance Schedule
6. Diagnostic & Troubleshooting (symptom → cause → corrective action)
7. Parts Catalog
8. Revision History

The domain's central risk (per the brief) is: *skipping a safety
prerequisite must be structurally enforced, not left to the model to
remember*. A generic fixed-size sliding-window chunker (e.g. "512 tokens,
50 overlap") would sometimes split a numbered safety step across two
chunks, or merge two unrelated steps into one chunk — in both cases,
retrieval could surface a safety instruction with its critical qualifier
("...only after the compressor is depressurized") separated from the
instruction itself.

## Decision
Chunk by **section type**, not by fixed token windows, using two different
rules:

- **Narrative sections** (Overview, Installation, Operating Procedures):
  split on Markdown headings first, then recursively on paragraph
  boundaries with a ~400-token target and ~15% overlap. This is the
  "normal RAG" case — prose tolerates a sliding window fine.

- **Structured/atomic sections** (Safety Prerequisites, Diagnostic &
  Troubleshooting steps, Maintenance Schedule rows): **one numbered
  item/table row = one chunk, never split, never merged with a sibling
  item.** No token-size target overrides this — a long safety step stays
  one chunk even above the narrative target size.

Every chunk carries structured metadata used later by retrieval and by the
Diagnostic & Safety Planner agent:

```
document_id, equipment_id, manual_revision, section_type
  (one of: overview | safety_prerequisite | installation | operating
   | maintenance | diagnostic | parts | revision_history),
section_title, order_index, source_ref (page/paragraph)
```

`section_type = safety_prerequisite` is the load-bearing field: the
application layer (not chunking, and not the LLM) is responsible for
always pulling every safety_prerequisite chunk tied to a matched
diagnostic procedure into context, regardless of vector-similarity rank.
That enforcement lives in the Diagnostic & Safety Planner use case — this
ADR only guarantees the chunk boundary never betrays that guarantee.

## Consequences
- Ingestion needs a lightweight structural parser (Markdown-header +
  numbered-list aware), not a naive character splitter. More upfront
  ingestion work; directly pays for the domain's core risk.
- Chunk sizes are uneven by design (a safety step might be 20 tokens, an
  overview paragraph 400). Retrieval/re-ranking must not assume uniform
  chunk length.
- This is our "one justified retrieval enhancement" candidate territory
  (metadata filtering) referenced in FR-2 — filtering by `section_type`
  is how the Safety Planner guarantees completeness rather than relying
  on similarity search alone. Documented fully once retrieval is built.
