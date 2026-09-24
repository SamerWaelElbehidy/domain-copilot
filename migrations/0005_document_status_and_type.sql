-- Revision awareness for D5 ("identify equipment & manual revision"):
-- superseded documents stay indexed (for audit and evaluation) but agent
-- retrieval is restricted to status = 'current'.

ALTER TABLE manual_documents
    ADD COLUMN doc_type TEXT NOT NULL DEFAULT 'manual'
        CHECK (doc_type IN ('manual', 'loto', 'bulletin', 'policy')),
    ADD COLUMN status TEXT NOT NULL DEFAULT 'current'
        CHECK (status IN ('current', 'superseded'));

-- Same equipment may legitimately have several documents of the same
-- revision label (manual Rev. A and its LOTO card Rev. A), so the old
-- (equipment_id, revision) uniqueness no longer holds.
ALTER TABLE manual_documents DROP CONSTRAINT manual_documents_equipment_id_revision_key;
