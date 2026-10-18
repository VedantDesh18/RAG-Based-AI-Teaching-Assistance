#!/usr/bin/env python3
"""Safely backfill or normalize legacy file_upload media references.

The default mode is read-only. ``--apply`` first creates a SQLite backup and
updates only rows whose old reference still matches the dry-run plan.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import videoqa.config as config_module
from videoqa.storage import (
    allowed_media_roots,
    media_file_is_readable,
    media_reference,
    resolve_media_path,
)


VIDEO_SIGNATURES = {
    ".mp4": "iso-bmff",
    ".m4v": "iso-bmff",
    ".mov": "iso-bmff",
    ".m4a": "iso-bmff",
    ".webm": "ebml",
    ".mkv": "ebml",
    ".avi": "avi",
    ".mp3": "mp3",
    ".wav": "wav",
}


@dataclass(frozen=True)
class PlannedChange:
    video_id: str
    title: str
    old_path: str | None
    new_path: str | None
    result: str
    detail: str


def _normalized_words(value: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", value.casefold())


def _file_has_supported_signature(path: Path) -> bool:
    kind = VIDEO_SIGNATURES.get(path.suffix.casefold())
    try:
        with path.open("rb") as source:
            header = source.read(16)
    except OSError:
        return False

    if kind == "iso-bmff":
        return len(header) >= 8 and header[4:8] == b"ftyp"
    if kind == "ebml":
        return header.startswith(bytes.fromhex("1A45DFA3"))
    if kind == "avi":
        return len(header) >= 12 and header[:4] == b"RIFF" and header[8:12] == b"AVI "
    if kind == "mp3":
        return header.startswith(b"ID3") or (len(header) >= 2 and header[0] == 0xFF and header[1] & 0xE0 == 0xE0)
    if kind == "wav":
        return len(header) >= 12 and header[:4] == b"RIFF" and header[8:12] == b"WAVE"
    return False


def _json_identity(video_id: str, json_root: Path) -> tuple[str, str] | None:
    """Resolve the exact legacy ID produced by migrate_from_joblib.py."""
    matches = [
        path
        for path in json_root.glob("*.json")
        if hashlib.md5(path.name.encode("utf-8")).hexdigest()[:11] == video_id
    ]
    if len(matches) != 1:
        return None
    try:
        data = json.loads(matches[0].read_text(encoding="utf-8"))
        chunks = data.get("chunks", [])
        if not chunks:
            return None
        number = str(chunks[0].get("number", ""))
        title = str(chunks[0].get("title", ""))
        if not number.isdigit() or not title.strip():
            return None
        return number, title
    except (OSError, json.JSONDecodeError, TypeError, AttributeError):
        return None


def _media_matches(number: str, title: str, media_root: Path, extensions: set[str]) -> list[Path]:
    expected = _normalized_words(title)
    if not expected:
        return []

    matches: list[Path] = []
    for path in media_root.rglob("*"):
        if not path.is_file() or path.suffix.casefold() not in extensions:
            continue
        name = path.stem
        prefix = re.match(r"^\s*(\d+)\s*[-_. ]+(.+)$", name)
        if not prefix or int(prefix.group(1)) != int(number):
            continue
        actual = _normalized_words(prefix.group(2))
        if actual[: len(expected)] != expected:
            continue
        suffix = actual[len(expected) :]
        # Some legacy downloads appended the source's short ID after the title.
        if suffix and not (len(suffix) == 1 and re.fullmatch(r"[a-z0-9]{6,11}", suffix[0])):
            continue
        if media_file_is_readable(path) and _file_has_supported_signature(path):
            matches.append(path.resolve())
    return matches


def plan_migration(db_path: Path, json_root: Path | None = None) -> list[PlannedChange]:
    roots = allowed_media_roots()
    media_root = roots["media"]
    legacy_root = roots["legacy"]
    json_root = json_root or Path(__file__).resolve().parents[1] / "jsons"
    extensions = {
        ext.casefold()
        for ext in config_module.config.get("ingestion", {}).get("supported_extensions", [])
    }

    uri = f"file:{db_path.resolve().as_posix()}?mode=ro"
    with sqlite3.connect(uri, uri=True) as connection:
        connection.row_factory = sqlite3.Row
        rows = connection.execute(
            "SELECT video_id, title, source_type, file_path FROM videos "
            "WHERE source_type = 'file_upload' ORDER BY video_id"
        ).fetchall()

    plan: list[PlannedChange] = []
    for row in rows:
        video_id = str(row["video_id"])
        title = str(row["title"])
        old_path = row["file_path"]
        resolved = resolve_media_path(old_path) if old_path else None

        raw_existing = False
        if old_path:
            try:
                raw_existing = Path(old_path).expanduser().exists()
            except (OSError, ValueError, TypeError):
                raw_existing = False

        if resolved and resolved.exists() and not media_file_is_readable(resolved):
            plan.append(PlannedChange(video_id, title, old_path, None, "unmatched", "Stored path exists but is not readable; it will not be replaced automatically"))
            continue
        if old_path and resolved is None and raw_existing:
            plan.append(PlannedChange(video_id, title, old_path, None, "unmatched", "Stored file exists outside the configured media roots; it will not be replaced"))
            continue

        if resolved and media_file_is_readable(resolved):
            root_name = next(
                (name for name, root in roots.items() if resolved.is_relative_to(root)),
                None,
            )
            if root_name is None or not _file_has_supported_signature(resolved):
                plan.append(PlannedChange(video_id, title, old_path, None, "unmatched", "Stored file is outside a usable configured media root or has an invalid signature"))
                continue
            canonical = media_reference(resolved, root_name)
            if old_path == canonical:
                plan.append(PlannedChange(video_id, title, old_path, canonical, "already-correct", "Stored file exists, is readable, and uses the canonical reference"))
            else:
                plan.append(PlannedChange(video_id, title, old_path, canonical, "matched", "Existing stored file verified; only its reference will be made portable"))
            continue

        identity = _json_identity(video_id, json_root)
        if identity is None:
            result = "missing" if old_path else "unmatched"
            detail = "Stored file is missing and no unique legacy JSON identity was found" if old_path else "No unique legacy JSON identity was found"
            plan.append(PlannedChange(video_id, title, old_path, None, result, detail))
            continue

        number, source_title = identity
        if _normalized_words(source_title) != _normalized_words(title):
            plan.append(PlannedChange(video_id, title, old_path, None, "unmatched", "Database title does not match the title in the JSON identified by the original video ID"))
            continue

        candidates = _media_matches(number, source_title, legacy_root, extensions)
        if len(candidates) > 1:
            plan.append(PlannedChange(video_id, title, old_path, None, "ambiguous", f"{len(candidates)} readable media files match the exact legacy sequence and title"))
        elif not candidates:
            result = "missing" if old_path else "unmatched"
            plan.append(PlannedChange(video_id, title, old_path, None, result, "No readable media file matches the exact legacy sequence and title"))
        else:
            candidate = candidates[0]
            reference = media_reference(candidate, "legacy")
            plan.append(PlannedChange(video_id, title, old_path, reference, "matched", f"Unique readable {candidate.suffix.lower()} matched through the legacy ID, JSON title, and sequence"))
    return plan


def _backup_database(db_path: Path) -> Path:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    backup_path = db_path.with_name(f"{db_path.name}.backup.{stamp}")
    with sqlite3.connect(f"file:{db_path.resolve().as_posix()}?mode=ro", uri=True) as source:
        with sqlite3.connect(backup_path) as destination:
            source.backup(destination)
    return backup_path


def apply_plan(db_path: Path, plan: list[PlannedChange]) -> Path:
    backup_path = _backup_database(db_path)
    updates = [item for item in plan if item.result == "matched" and item.new_path != item.old_path]
    with sqlite3.connect(db_path) as connection:
        try:
            connection.execute("BEGIN IMMEDIATE")
            for item in updates:
                cursor = connection.execute(
                    "UPDATE videos SET file_path = ? WHERE video_id = ? AND file_path IS ?",
                    (item.new_path, item.video_id, item.old_path),
                )
                if cursor.rowcount != 1:
                    raise RuntimeError(f"Record {item.video_id} changed after the migration plan; no further updates were applied")
            connection.commit()
        except Exception:
            connection.rollback()
            raise
    return backup_path


def _database_path(argument: str | None) -> Path:
    value = argument or config_module.config.get("paths", {}).get("db", "data/db/videoqa.db")
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = Path.cwd() / path
    return path.resolve()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", help="SQLite database to inspect (defaults to configured DB_PATH)")
    parser.add_argument("--json-root", type=Path, help="Legacy jsons/ directory used to verify original video IDs")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", help="Read-only report (the default)")
    mode.add_argument("--apply", action="store_true", help="Back up the database, then apply unambiguous matches")
    args = parser.parse_args()

    db_path = _database_path(args.db)
    if not db_path.is_file():
        parser.error(f"Database does not exist: {db_path}")
    plan = plan_migration(db_path, args.json_root)
    for item in plan:
        proposed = f" -> {item.new_path}" if item.new_path else ""
        print(f"{item.result.upper():15} {item.video_id}  {item.title!r}{proposed}  ({item.detail})")

    counts = {name: sum(item.result == name for item in plan) for name in ("matched", "unmatched", "ambiguous", "missing", "already-correct")}
    print("\nDry-run summary: " + ", ".join(f"{name}={count}" for name, count in counts.items()))
    if args.apply:
        backup_path = apply_plan(db_path, plan)
        print(f"Backup: {backup_path}")
        print(f"Applied {sum(item.result == 'matched' and item.new_path != item.old_path for item in plan)} path updates.")
    else:
        print("No database changes made. Review the report, then rerun with --apply to make the listed updates.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
