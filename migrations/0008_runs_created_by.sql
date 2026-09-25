-- Who raised the run. Needed for ownership checks (a technician sees only
-- their own runs) and separation of duties (the requester cannot approve
-- their own work order).
ALTER TABLE runs ADD COLUMN created_by TEXT;
CREATE INDEX idx_runs_created_by ON runs(created_by);
CREATE INDEX idx_runs_state ON runs(state);
