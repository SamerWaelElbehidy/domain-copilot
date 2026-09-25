-- Accounts for FR-8 (authentication plus roles enforced server-side).
-- Passwords are stored only as scrypt hashes.

CREATE TABLE users (
    user_id        TEXT PRIMARY KEY,
    username       TEXT NOT NULL UNIQUE,
    role           TEXT NOT NULL CHECK (role IN ('technician', 'supervisor', 'admin')),
    disabled       BOOLEAN NOT NULL DEFAULT FALSE,
    password_hash  TEXT NOT NULL,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Object-ownership checks (OWASP broken access control): who raised each run.
ALTER TABLE runs ADD COLUMN created_by TEXT REFERENCES users(user_id);
CREATE INDEX idx_runs_created_by ON runs(created_by);
