-- Persists the Run/RunStep domain entities (ADR-0005/0006): the
-- orchestration state machine and the T4 hash-chained audit/replay log.
-- run_steps is append-only by convention (enforced in the application
-- layer via Run.record_step's hash-chain check) -- the database itself
-- does not forbid UPDATE/DELETE here, since Postgres has no native
-- "insert-only" table mode; that gap is documented in docs/SECURITY.md.

CREATE TABLE runs (
    run_id        TEXT PRIMARY KEY,
    equipment_id  TEXT REFERENCES equipment(equipment_id),
    started_at    TIMESTAMPTZ NOT NULL,
    state         TEXT NOT NULL
);

CREATE TABLE run_steps (
    run_id            TEXT NOT NULL REFERENCES runs(run_id),
    step_index        INTEGER NOT NULL,
    name              TEXT NOT NULL,
    agent_name        TEXT,
    provider_used     TEXT,
    input_snapshot    JSONB NOT NULL,
    output_snapshot   JSONB NOT NULL,
    input_tokens      INTEGER NOT NULL DEFAULT 0,
    output_tokens     INTEGER NOT NULL DEFAULT 0,
    started_at        TIMESTAMPTZ NOT NULL,
    finished_at       TIMESTAMPTZ NOT NULL,
    status            TEXT NOT NULL,
    step_hash         TEXT NOT NULL,
    PRIMARY KEY (run_id, step_index)
);

CREATE INDEX idx_run_steps_run ON run_steps(run_id);
