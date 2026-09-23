-- Keyword side of hybrid retrieval (ADR-0004): Postgres full-text search
-- over the same chunks Qdrant holds as vectors. chunk_id must match the
-- point id used in Qdrant so RRF fusion can join results by that id.

CREATE TABLE chunks_fts (
    chunk_id        TEXT PRIMARY KEY,
    document_id     TEXT NOT NULL REFERENCES manual_documents(document_id),
    equipment_id    TEXT NOT NULL REFERENCES equipment(equipment_id),
    manual_revision TEXT NOT NULL,
    section_type    TEXT NOT NULL,
    section_title   TEXT NOT NULL,
    content         TEXT NOT NULL,
    order_index     INTEGER NOT NULL,
    source_ref      TEXT NOT NULL,
    search_vector   TSVECTOR GENERATED ALWAYS AS (to_tsvector('english', content)) STORED
);

CREATE INDEX idx_chunks_fts_search_vector ON chunks_fts USING GIN (search_vector);
CREATE INDEX idx_chunks_fts_document ON chunks_fts(document_id);
CREATE INDEX idx_chunks_fts_section_type ON chunks_fts(section_type);
