CREATE TABLE IF NOT EXISTS chat_messages (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id  TEXT NOT NULL REFERENCES chat_sessions(session_id) ON DELETE CASCADE,
    role        TEXT NOT NULL CHECK(role IN ('user', 'assistant')),
    content     TEXT NOT NULL,
    citations   TEXT,
    created_at  TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS chat_messages_session_created_idx
ON chat_messages(session_id, created_at);
