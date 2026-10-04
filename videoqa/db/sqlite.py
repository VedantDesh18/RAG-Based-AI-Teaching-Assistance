import sqlite3
import os
from pathlib import Path
from videoqa.config import config

def get_db_path():
    db_path = config.get("paths", {}).get("db", "data/db/videoqa.db")
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    return db_path

def get_connection():
    conn = sqlite3.connect(get_db_path(), timeout=10)
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.execute("PRAGMA journal_mode = WAL;")
    conn.row_factory = sqlite3.Row
    return conn

def run_migrations():
    conn = get_connection()
    try:
        migration_dir = Path("db/migrations")
        if not migration_dir.exists():
            return
        
        # Simple migration runner: just execute them in order.
        # Idempotency is handled by IF NOT EXISTS in the SQL script.
        migrations = sorted([f for f in os.listdir(migration_dir) if f.endswith('.sql')])
        for migration in migrations:
            with open(migration_dir / migration, "r", encoding="utf-8") as f:
                sql = f.read()
            conn.executescript(sql)
        conn.commit()
    finally:
        conn.close()

# Videos CRUD
def upsert_video(video: dict):
    conn = get_connection()
    try:
        conn.execute("""
            INSERT INTO videos (id, video_id, source_type, title, duration_seconds, status, created_at, updated_at)
            VALUES (:id, :video_id, :source_type, :title, :duration_seconds, :status, :created_at, :updated_at)
            ON CONFLICT(video_id) DO UPDATE SET
                title=excluded.title,
                duration_seconds=excluded.duration_seconds,
                status=excluded.status,
                updated_at=excluded.updated_at
        """, video)
        conn.commit()
    finally:
        conn.close()

def delete_video_sqlite(video_id: str):
    conn = get_connection()
    try:
        conn.execute("DELETE FROM chunks WHERE video_id = ?", (video_id,))
        conn.execute("DELETE FROM transcript_segments WHERE video_id = ?", (video_id,))
        conn.execute("DELETE FROM videos WHERE video_id = ?", (video_id,))
        conn.commit()
    finally:
        conn.close()

# Transcript Segments
def insert_transcript_segments(segments: list[dict]):
    if not segments: return
    conn = get_connection()
    try:
        conn.executemany("""
            INSERT INTO transcript_segments (video_id, segment_index, start_seconds, end_seconds, text_original, text_english)
            VALUES (:video_id, :segment_index, :start_seconds, :end_seconds, :text_original, :text_english)
            ON CONFLICT(video_id, segment_index) DO NOTHING
        """, segments)
        conn.commit()
    finally:
        conn.close()

# Chunks
def insert_chunks(chunks: list[dict]):
    if not chunks: return
    conn = get_connection()
    try:
        conn.executemany("""
            INSERT INTO chunks (chunk_id, video_id, chunk_index, start_seconds, end_seconds, text, text_original, word_count, language)
            VALUES (:chunk_id, :video_id, :chunk_index, :start_seconds, :end_seconds, :text, :text_original, :word_count, :language)
            ON CONFLICT(video_id, chunk_index) DO UPDATE SET
                chunk_id=excluded.chunk_id,
                start_seconds=excluded.start_seconds,
                end_seconds=excluded.end_seconds,
                text=excluded.text,
                text_original=excluded.text_original,
                word_count=excluded.word_count,
                language=excluded.language
        """, chunks)
        conn.commit()
    finally:
        conn.close()

def search_chunks_bm25(query: str, limit: int = 5):
    conn = get_connection()
    try:
        cursor = conn.execute("""
            SELECT c.*, fts.rank 
            FROM chunks_fts fts
            JOIN chunks c ON fts.rowid = c.id
            WHERE chunks_fts MATCH ?
            ORDER BY rank
            LIMIT ?
        """, (query, limit))
        return [dict(row) for row in cursor.fetchall()]
    finally:
        conn.close()

# Chat Sessions
def upsert_chat_session(session: dict):
    conn = get_connection()
    try:
        conn.execute("""
            INSERT INTO chat_sessions (session_id, video_id, created_at, updated_at)
            VALUES (:session_id, :video_id, :created_at, :updated_at)
            ON CONFLICT(session_id) DO UPDATE SET updated_at=excluded.updated_at
        """, session)
        conn.commit()
    finally:
        conn.close()
