-- Per-request accounting (FR-9): every model call with tokens, cost, latency
-- and the correlation id that links it to the request and the run.
CREATE TABLE llm_calls (
    call_id         BIGSERIAL PRIMARY KEY,
    correlation_id  TEXT NOT NULL,
    user_id         TEXT REFERENCES users(user_id),
    run_id          TEXT REFERENCES runs(run_id),
    purpose         TEXT NOT NULL,
    provider        TEXT NOT NULL,
    model           TEXT NOT NULL,
    operation       TEXT NOT NULL CHECK (operation IN ('complete', 'stream', 'embed')),
    input_tokens    INTEGER NOT NULL DEFAULT 0,
    output_tokens   INTEGER NOT NULL DEFAULT 0,
    cost_usd        NUMERIC(12, 6) NOT NULL DEFAULT 0,
    latency_ms      INTEGER NOT NULL DEFAULT 0,
    status          TEXT NOT NULL CHECK (status IN ('ok', 'error', 'cancelled')),
    created_at      TIMESTAMPTZ NOT NULL
);
CREATE INDEX idx_llm_calls_correlation ON llm_calls(correlation_id);
CREATE INDEX idx_llm_calls_user_time ON llm_calls(user_id, created_at);
CREATE INDEX idx_llm_calls_run ON llm_calls(run_id);

-- Persistent session history (FR-7). A session belongs to one user and is
-- only ever read back through that user's id (object-ownership check).
CREATE TABLE chat_sessions (
    session_id  TEXT PRIMARY KEY,
    user_id     TEXT NOT NULL REFERENCES users(user_id),
    title       TEXT NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL
);
CREATE INDEX idx_chat_sessions_user ON chat_sessions(user_id, created_at DESC);

CREATE TABLE chat_messages (
    message_id  BIGSERIAL PRIMARY KEY,
    session_id  TEXT NOT NULL REFERENCES chat_sessions(session_id) ON DELETE CASCADE,
    role        TEXT NOT NULL CHECK (role IN ('user', 'assistant')),
    content     TEXT NOT NULL,
    status      TEXT NOT NULL DEFAULT 'answered',
    citations   JSONB NOT NULL DEFAULT '[]',
    detail      TEXT,
    created_at  TIMESTAMPTZ NOT NULL
);
CREATE INDEX idx_chat_messages_session ON chat_messages(session_id, message_id);
