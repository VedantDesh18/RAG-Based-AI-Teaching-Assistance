import sqlite3
import os
import json
from pathlib import Path
import videoqa.config as config_module

def get_db_path():
    db_path = config_module.config.get("paths", {}).get("db", "data/db/videoqa.db")
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
        # Ensure stored chunk_count reflects the authoritative count of actual indexed chunks
        conn.execute("""
            UPDATE videos
            SET chunk_count = (SELECT COUNT(*) FROM chunks c WHERE c.video_id = videos.video_id)
            WHERE chunk_count IS NULL OR chunk_count != (SELECT COUNT(*) FROM chunks c WHERE c.video_id = videos.video_id)
        """)
        conn.commit()
    finally:
        conn.close()

# Videos CRUD
def upsert_video(video: dict):
    conn = get_connection()
    try:
        conn.execute("""
            INSERT INTO videos (
                id, video_id, source_type, source_url, title, channel, duration_seconds, 
                thumbnail_url, upload_date, description, detected_language, file_path, 
                status, error_message, created_at, updated_at
            )
            VALUES (
                :id, :video_id, :source_type, :source_url, :title, :channel, :duration_seconds, 
                :thumbnail_url, :upload_date, :description, :detected_language, :file_path, 
                :status, :error_message, :created_at, :updated_at
            )
            ON CONFLICT(video_id) DO UPDATE SET
                title=excluded.title,
                channel=excluded.channel,
                duration_seconds=excluded.duration_seconds,
                thumbnail_url=excluded.thumbnail_url,
                upload_date=excluded.upload_date,
                description=excluded.description,
                detected_language=excluded.detected_language,
                file_path=COALESCE(excluded.file_path, videos.file_path),
                status=excluded.status,
                error_message=excluded.error_message,
                updated_at=excluded.updated_at
        """, {
            'id': video.get('id'),
            'video_id': video.get('video_id'),
            'source_type': video.get('source_type'),
            'source_url': video.get('source_url'),
            'title': video.get('title'),
            'channel': video.get('channel'),
            'duration_seconds': video.get('duration_seconds', 0.0),
            'thumbnail_url': video.get('thumbnail_url'),
            'upload_date': video.get('upload_date'),
            'description': video.get('description'),
            'detected_language': video.get('detected_language'),
            'file_path': video.get('file_path'),
            'status': video.get('status', 'queued'),
            'error_message': video.get('error_message'),
            'created_at': video.get('created_at'),
            'updated_at': video.get('updated_at')
        })
        conn.commit()
    finally:
        conn.close()

def insert_video_if_absent(video: dict) -> bool:
    """Insert a newly uploaded video once, so duplicate uploads queue once."""
    conn = get_connection()
    try:
        cursor = conn.execute(
            """INSERT INTO videos (
                id, video_id, source_type, source_url, title, channel, duration_seconds,
                thumbnail_url, upload_date, description, detected_language, file_path,
                status, error_message, created_at, updated_at
            ) VALUES (
                :id, :video_id, :source_type, :source_url, :title, :channel, :duration_seconds,
                :thumbnail_url, :upload_date, :description, :detected_language, :file_path,
                :status, :error_message, :created_at, :updated_at
            ) ON CONFLICT(video_id) DO NOTHING""",
            {
                "id": video.get("id"),
                "video_id": video.get("video_id"),
                "source_type": video.get("source_type"),
                "source_url": video.get("source_url"),
                "title": video.get("title"),
                "channel": video.get("channel"),
                "duration_seconds": video.get("duration_seconds", 0.0),
                "thumbnail_url": video.get("thumbnail_url"),
                "upload_date": video.get("upload_date"),
                "description": video.get("description"),
                "detected_language": video.get("detected_language"),
                "file_path": video.get("file_path"),
                "status": video.get("status", "queued"),
                "error_message": video.get("error_message"),
                "created_at": video.get("created_at"),
                "updated_at": video.get("updated_at"),
            },
        )
        conn.commit()
        return cursor.rowcount == 1
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

def update_video_file_path(video_id: str, file_path: str, updated_at: str) -> None:
    conn = get_connection()
    try:
        conn.execute(
            "UPDATE videos SET file_path = ?, updated_at = ? WHERE video_id = ?",
            (file_path, updated_at, video_id),
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

def update_video_metadata(video_id: str, metadata: dict) -> None:
    """Update extractor metadata without changing job status or media path."""
    allowed = (
        "source_url", "title", "channel", "duration_seconds", "thumbnail_url",
        "upload_date", "description", "detected_language", "updated_at",
    )
    fields = [name for name in allowed if name in metadata]
    if not fields:
        return
    assignments = ", ".join(f"{name} = ?" for name in fields)
    values = [metadata[name] for name in fields]
    conn = get_connection()
    try:
        conn.execute(f"UPDATE videos SET {assignments} WHERE video_id = ?", (*values, video_id))
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

def update_video_status(
    video_id: str,
    status: str,
    updated_at: str,
    error_message: str | None = None,
    allowed_current_statuses: set[str] | None = None,
) -> bool:
    """Update job state only, preserving all video and media metadata."""
    conn = get_connection()
    try:
        sql = "UPDATE videos SET status = ?, error_message = ?, updated_at = ? WHERE video_id = ?"
        params: list = [status, error_message, updated_at, video_id]
        if allowed_current_statuses is not None:
            placeholders = ",".join("?" for _ in allowed_current_statuses)
            sql += f" AND status IN ({placeholders})"
            params.extend(sorted(allowed_current_statuses))
        elif status != "cancelled":
            # A cancellation racing an ingestion-stage update remains authoritative.
            sql += " AND status != 'cancelled'"
        cursor = conn.execute(sql, params)
        conn.commit()
        return cursor.rowcount == 1
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

def update_video_duration(video_id: str, duration_seconds: float, updated_at: str) -> None:
    conn = get_connection()
    try:
        conn.execute(
            "UPDATE videos SET duration_seconds = ?, updated_at = ? WHERE video_id = ?",
            (duration_seconds, updated_at, video_id),
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

def delete_video_sqlite(video_id: str) -> int:
    conn = get_connection()
    try:
        chunk_count = conn.execute("SELECT COUNT(*) FROM chunks WHERE video_id = ?", (video_id,)).fetchone()[0]
        conn.execute("DELETE FROM chat_messages WHERE session_id IN (SELECT session_id FROM chat_sessions WHERE video_id = ?)", (video_id,))
        conn.execute("DELETE FROM chat_sessions WHERE video_id = ?", (video_id,))
        conn.execute("DELETE FROM chunks WHERE video_id = ?", (video_id,))
        conn.execute("DELETE FROM transcript_segments WHERE video_id = ?", (video_id,))
        conn.execute("DELETE FROM videos WHERE video_id = ?", (video_id,))
        conn.commit()
        return chunk_count
    finally:
        conn.close()

def get_video(video_id: str):
    conn = get_connection()
    try:
        # Legacy and migrated rows can have a stale `videos.chunk_count` value.
        # The chunks table is authoritative for both chat eligibility and query
        # validation, just as it is for the library listing.
        cursor = conn.execute("""
            SELECT v.*,
                   (SELECT COUNT(*) FROM chunks c WHERE c.video_id = v.video_id) AS calculated_chunk_count
            FROM videos v
            WHERE v.video_id = ?
        """, (video_id,))
        row = cursor.fetchone()
        if not row:
            return None
        video = dict(row)
        video['chunk_count'] = video.pop('calculated_chunk_count', 0)
        return video
    finally:
        conn.close()

def list_videos() -> list[dict]:
    """Return lightweight video records with authoritative chunk counts."""
    conn = get_connection()
    try:
        cursor = conn.execute("""
            SELECT v.*, COUNT(c.id) AS calculated_chunk_count
            FROM videos v
            LEFT JOIN chunks c ON c.video_id = v.video_id
            GROUP BY v.video_id
            ORDER BY v.created_at DESC
        """)
        videos = []
        for row in cursor.fetchall():
            item = dict(row)
            item['chunk_count'] = item.pop('calculated_chunk_count', 0)
            videos.append(item)
        return videos
    finally:
        conn.close()

def get_transcript_segments(video_id: str) -> list[dict]:
    conn = get_connection()
    try:
        cursor = conn.execute("""
            SELECT segment_index, start_seconds, end_seconds, text_original, text_english, language
            FROM transcript_segments
            WHERE video_id = ?
            ORDER BY segment_index ASC
        """, (video_id,))
        return [dict(row) for row in cursor.fetchall()]
    finally:
        conn.close()

def reset_video_content(video_id: str) -> None:
    """Remove derived data before a real ingestion retry recreates it."""
    conn = get_connection()
    try:
        conn.execute("DELETE FROM chunks WHERE video_id = ?", (video_id,))
        conn.execute("DELETE FROM transcript_segments WHERE video_id = ?", (video_id,))
        conn.execute("UPDATE videos SET chunk_count = 0 WHERE video_id = ?", (video_id,))
        conn.commit()
    finally:
        conn.close()

def claim_video_retry(video_id: str, updated_at: str, max_retries: int = 3) -> dict | None:
    """Atomically claim a failed/cancelled job and clear its derived rows."""
    conn = get_connection()
    try:
        conn.execute("BEGIN IMMEDIATE")
        cursor = conn.execute(
            """UPDATE videos
               SET status = 'queued', error_message = NULL,
                   retry_count = COALESCE(retry_count, 0) + 1, updated_at = ?, chunk_count = 0
               WHERE video_id = ? AND status IN ('failed', 'cancelled')
                 AND COALESCE(retry_count, 0) < ?""",
            (updated_at, video_id, max_retries),
        )
        if cursor.rowcount != 1:
            conn.rollback()
            return None
        conn.execute("DELETE FROM chunks WHERE video_id = ?", (video_id,))
        conn.execute("DELETE FROM transcript_segments WHERE video_id = ?", (video_id,))
        row = conn.execute("SELECT * FROM videos WHERE video_id = ?", (video_id,)).fetchone()
        conn.commit()
        return dict(row) if row else None
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

def increment_retry_count(video_id: str) -> int:
    conn = get_connection()
    try:
        conn.execute("UPDATE videos SET retry_count = COALESCE(retry_count, 0) + 1 WHERE video_id = ?", (video_id,))
        row = conn.execute("SELECT retry_count FROM videos WHERE video_id = ?", (video_id,)).fetchone()
        conn.commit()
        return int(row[0]) if row else 0
    finally:
        conn.close()

def set_chunk_count(video_id: str, count: int) -> None:
    conn = get_connection()
    try:
        conn.execute("UPDATE videos SET chunk_count = ? WHERE video_id = ?", (count, video_id))
        conn.commit()
    finally:
        conn.close()

# Transcript Segments
def insert_transcript_segments(segments: list[dict]):
    if not segments: return
    conn = get_connection()
    try:
        conn.executemany("""
            INSERT INTO transcript_segments (video_id, segment_index, start_seconds, end_seconds, text_original, text_english, language)
            VALUES (:video_id, :segment_index, :start_seconds, :end_seconds, :text_original, :text_english, :language)
            ON CONFLICT(video_id, segment_index) DO UPDATE SET
                text_original=excluded.text_original,
                text_english=excluded.text_english,
                language=excluded.language
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
        video_id = chunks[0]['video_id']
        conn.execute(
            "UPDATE videos SET chunk_count = (SELECT COUNT(*) FROM chunks WHERE video_id = ?) WHERE video_id = ?",
            (video_id, video_id)
        )
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

def get_chat_session(session_id: str) -> dict | None:
    conn = get_connection()
    try:
        row = conn.execute("SELECT * FROM chat_sessions WHERE session_id = ?", (session_id,)).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()

def insert_chat_message(session_id: str, role: str, content: str, created_at: str, citations: list | None = None) -> None:
    conn = get_connection()
    try:
        conn.execute("""
            INSERT INTO chat_messages (session_id, role, content, citations, created_at)
            VALUES (?, ?, ?, ?, ?)
        """, (session_id, role, content, json.dumps(citations or []), created_at))
        conn.execute("UPDATE chat_sessions SET updated_at = ? WHERE session_id = ?", (created_at, session_id))
        conn.commit()
    finally:
        conn.close()

def get_chat_messages(session_id: str, limit: int | None = None) -> list[dict]:
    conn = get_connection()
    try:
        sql = "SELECT id, role, content, citations, created_at FROM chat_messages WHERE session_id = ? ORDER BY id ASC"
        params: list = [session_id]
        if limit:
            sql = """SELECT * FROM (
                SELECT id, role, content, citations, created_at
                FROM chat_messages WHERE session_id = ? ORDER BY id DESC LIMIT ?
            ) ORDER BY id ASC"""
            params.append(limit)
        rows = conn.execute(sql, params).fetchall()
        messages = []
        for row in rows:
            item = dict(row)
            try:
                item['citations'] = json.loads(item['citations'] or '[]')
            except json.JSONDecodeError:
                item['citations'] = []
            messages.append(item)
        return messages
    finally:
        conn.close()

def list_chat_sessions() -> list[dict]:
    conn = get_connection()
    try:
        rows = conn.execute("""
            SELECT s.session_id, s.video_id, s.created_at, s.updated_at, v.title AS video_title,
                (SELECT content FROM chat_messages WHERE session_id = s.session_id AND role = 'user' ORDER BY id DESC LIMIT 1) AS last_question,
                (SELECT content FROM chat_messages WHERE session_id = s.session_id AND role = 'assistant' ORDER BY id DESC LIMIT 1) AS last_answer
            FROM chat_sessions s
            LEFT JOIN videos v ON v.video_id = s.video_id
            ORDER BY s.updated_at DESC
        """).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()
