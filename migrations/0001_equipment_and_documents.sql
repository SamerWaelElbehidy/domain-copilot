-- Relational metadata for DocumentRepository (ADR-0001 port).
-- Ingestion status columns support FR-1's "per-document status and
-- failure reporting" requirement.

CREATE TABLE equipment (
    equipment_id  TEXT PRIMARY KEY,
    name          TEXT NOT NULL,
    model_number  TEXT NOT NULL,
    category      TEXT NOT NULL
);

CREATE TABLE manual_documents (
    document_id     TEXT PRIMARY KEY,
    equipment_id    TEXT NOT NULL REFERENCES equipment(equipment_id),
    revision        TEXT NOT NULL,
    effective_date  DATE NOT NULL,
    title           TEXT NOT NULL,
    ingestion_status TEXT NOT NULL DEFAULT 'pending'
        CHECK (ingestion_status IN ('pending', 'ingested', 'failed')),
    ingestion_error  TEXT,
    ingested_at      TIMESTAMPTZ,
    UNIQUE (equipment_id, revision)
);

CREATE INDEX idx_manual_documents_equipment ON manual_documents(equipment_id);
