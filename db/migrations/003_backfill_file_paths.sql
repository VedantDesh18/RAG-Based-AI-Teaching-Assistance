-- Allow duration_seconds to have a default value of 0 for file uploads
-- where the duration isn't known until ffprobe runs.
-- SQLite doesn't support ALTER COLUMN, but the existing schema already
-- has NOT NULL with no DEFAULT.  The column itself works fine because
-- upsert_video always supplies the value.  No DDL change needed here.

-- This migration file exists as a placeholder to record that the
-- file_path backfill for legacy file_upload videos was handled by
-- scripts/backfill_file_paths.py, which is idempotent and safe to
-- run repeatedly.
