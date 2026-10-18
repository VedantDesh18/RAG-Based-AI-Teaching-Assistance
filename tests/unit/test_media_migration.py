import hashlib
import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path

import videoqa.config as config_module
from scripts.backfill_file_paths import apply_plan, plan_migration


def _video_id(filename: str) -> str:
    return hashlib.md5(filename.encode("utf-8")).hexdigest()[:11]


def _insert_video(connection: sqlite3.Connection, video_id: str, title: str, file_path: str | None = None) -> None:
    now = datetime.now(timezone.utc).isoformat()
    connection.execute(
        """INSERT INTO videos (id, video_id, source_type, title, duration_seconds, file_path, status, created_at, updated_at)
           VALUES (?, ?, 'file_upload', ?, 0, ?, 'ready', ?, ?)""",
        (str(uuid.uuid4()), video_id, title, file_path, now, now),
    )


def _add_legacy_json(json_root: Path, number: str, title: str) -> str:
    filename = f"{number}-{title}.mp3.json"
    payload = {"chunks": [{"number": number, "title": title, "start": 0, "end": 1, "text": "lesson"}]}
    (json_root / filename).write_text(json.dumps(payload), encoding="utf-8")
    return _video_id(filename)


def _add_webm(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(bytes.fromhex("1A45DFA3") + b"synthetic-media")


def _setup(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    media_root = tmp_path / "data" / "media"
    legacy_root = tmp_path / "videos"
    json_root = tmp_path / "jsons"
    media_root.mkdir(parents=True)
    legacy_root.mkdir()
    json_root.mkdir()
    db_path = tmp_path / "test.sqlite"
    config = {
        "paths": {"db": str(db_path), "media": str(media_root), "legacy_media": str(legacy_root)},
        "ingestion": {"supported_extensions": [".webm", ".mp4", ".mkv"]},
    }
    monkeypatch.setattr(config_module, "config", config)
    with sqlite3.connect(db_path) as connection:
        schema = (Path(__file__).resolve().parents[2] / "db" / "migrations" / "001_initial.sql").read_text(encoding="utf-8")
        connection.executescript(schema)
    return db_path, json_root, legacy_root


def test_migration_matches_exact_id_title_and_sequence_and_is_idempotent(tmp_path, monkeypatch):
    db_path, json_root, legacy_root = _setup(tmp_path, monkeypatch)
    video_id = _add_legacy_json(json_root, "01", "alpha lesson")
    media_file = legacy_root / "01-alpha-lesson.webm"
    _add_webm(media_file)
    with sqlite3.connect(db_path) as connection:
        _insert_video(connection, video_id, "alpha lesson")
        _insert_video(connection, "unrelated-video", "unrelated", None)
        connection.execute(
            "INSERT INTO videos (id,video_id,source_type,title,duration_seconds,status,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?)",
            (str(uuid.uuid4()), "youtube-item", "youtube", "Unrelated YouTube", 1, "ready", "now", "now"),
        )

    plan = plan_migration(db_path, json_root)
    matched = next(item for item in plan if item.video_id == video_id)
    assert matched.result == "matched"
    assert matched.new_path == "legacy/01-alpha-lesson.webm"
    assert next(item for item in plan if item.video_id == "unrelated-video").result == "unmatched"

    backup = apply_plan(db_path, plan)
    assert backup.is_file()
    with sqlite3.connect(db_path) as connection:
        repaired = connection.execute("SELECT file_path FROM videos WHERE video_id = ?", (video_id,)).fetchone()[0]
        untouched = connection.execute("SELECT file_path FROM videos WHERE video_id = 'unrelated-video'").fetchone()[0]
        unrelated_ids = connection.execute("SELECT video_id FROM videos WHERE source_type = 'youtube'").fetchall()
    assert repaired == "legacy/01-alpha-lesson.webm"
    assert untouched is None
    assert unrelated_ids == [("youtube-item",)]
    second_run = plan_migration(db_path, json_root)
    assert next(item for item in second_run if item.video_id == video_id).result == "already-correct"


def test_migration_reports_ambiguous_candidates_without_modifying_record(tmp_path, monkeypatch):
    db_path, json_root, legacy_root = _setup(tmp_path, monkeypatch)
    video_id = _add_legacy_json(json_root, "02", "beta lesson")
    _add_webm(legacy_root / "02-beta-lesson.webm")
    _add_webm(legacy_root / "02-beta-lesson-abcdef.webm")
    with sqlite3.connect(db_path) as connection:
        _insert_video(connection, video_id, "beta lesson")

    plan = plan_migration(db_path, json_root)
    item = plan[0]
    assert item.result == "ambiguous"
    assert item.new_path is None
    apply_plan(db_path, plan)
    with sqlite3.connect(db_path) as connection:
        assert connection.execute("SELECT file_path FROM videos WHERE video_id = ?", (video_id,)).fetchone()[0] is None


def test_migration_unmatched_record_stays_unchanged(tmp_path, monkeypatch):
    db_path, json_root, _ = _setup(tmp_path, monkeypatch)
    with sqlite3.connect(db_path) as connection:
        _insert_video(connection, "no-json-record", "No source metadata")

    plan = plan_migration(db_path, json_root)
    assert plan[0].result == "unmatched"
    apply_plan(db_path, plan)
    with sqlite3.connect(db_path) as connection:
        assert connection.execute("SELECT file_path FROM videos WHERE video_id = 'no-json-record'").fetchone()[0] is None
