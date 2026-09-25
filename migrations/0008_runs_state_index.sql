-- Approvals queue and run lists filter by state. (created_by and its index came in
-- with 0006, where the ownership model was introduced.)
CREATE INDEX idx_runs_state ON runs(state);
