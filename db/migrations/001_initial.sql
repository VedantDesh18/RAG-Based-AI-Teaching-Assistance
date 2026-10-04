CREATE TABLE IF NOT EXISTS videos (
    id              TEXT PRIMARY KEY,               -- UUID
    video_id        TEXT UNIQUE,                     -- YouTube ID or hash of file
    source_type     TEXT NOT NULL,                   -- 'youtube' | 'direct_url' | 'file_upload'
    source_url      TEXT,
    title           TEXT NOT NULL,
    channel         TEXT,
    duration_seconds REAL NOT NULL,
    thumbnail_url   TEXT,
    upload_date     TEXT,
    description     TEXT,
    detected_language TEXT,                          -- ISO 639-1
    file_path       TEXT,                            -- local path to media (if uploaded)
    status          TEXT NOT NULL DEFAULT 'queued',  -- queued|downloading|transcribing|chunking|embedding|ready|failed
    error_message   TEXT,
    retry_count     INTEGER DEFAULT 0,
    chunk_count     INTEGER DEFAULT 0,
    caption_source  TEXT,                            -- 'youtube_manual'|'youtube_auto'|'whisper'
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS transcript_segments (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    video_id        TEXT NOT NULL REFERENCES videos(video_id),
    segment_index   INTEGER NOT NULL,
    start_seconds   REAL NOT NULL,
    end_seconds     REAL NOT NULL,
    text_original   TEXT,                            -- original language transcript
    text_english    TEXT,                            -- English translation
    language        TEXT,
    UNIQUE(video_id, segment_index)
);

CREATE TABLE IF NOT EXISTS chunks (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    chunk_id        TEXT UNIQUE NOT NULL,            -- UUID
    video_id        TEXT NOT NULL REFERENCES videos(video_id),
    chunk_index     INTEGER NOT NULL,
    start_seconds   REAL NOT NULL,
    end_seconds     REAL NOT NULL,
    text            TEXT NOT NULL,                   -- text used for embedding (English by default)
    text_original   TEXT,                            -- original language text
    word_count      INTEGER NOT NULL,
    language        TEXT,
    UNIQUE(video_id, chunk_index)
);

CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(
    text, chunk_id UNINDEXED, content='chunks', content_rowid='id'
);

CREATE TRIGGER IF NOT EXISTS chunks_ai AFTER INSERT ON chunks BEGIN
  INSERT INTO chunks_fts(rowid, text, chunk_id) VALUES (new.id, new.text, new.chunk_id);
END;
CREATE TRIGGER IF NOT EXISTS chunks_ad AFTER DELETE ON chunks BEGIN
  INSERT INTO chunks_fts(chunks_fts, rowid, text, chunk_id) VALUES('delete', old.id, old.text, old.chunk_id);
END;
CREATE TRIGGER IF NOT EXISTS chunks_au AFTER UPDATE ON chunks BEGIN
  INSERT INTO chunks_fts(chunks_fts, rowid, text, chunk_id) VALUES('delete', old.id, old.text, old.chunk_id);
  INSERT INTO chunks_fts(rowid, text, chunk_id) VALUES (new.id, new.text, new.chunk_id);
END;

CREATE TABLE IF NOT EXISTS chat_sessions (
    session_id      TEXT PRIMARY KEY,
    video_id        TEXT,                            -- NULL for cross-library queries
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL
);
