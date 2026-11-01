"""Tests for video upload, database persistence, and media playback.

These tests use the FastAPI TestClient and a temporary SQLite database so
they can run without starting a separate server process.
"""
import io
import shutil
import sqlite3
import subprocess
import tempfile
import uuid
from functools import lru_cache
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _isolated_data_dir(tmp_path, monkeypatch):
    """Run every test with a fresh data directory and DB."""
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    (data_dir / "db").mkdir()
    (data_dir / "media").mkdir()

    # Create a videos/ directory for legacy-style video files
    videos_dir = tmp_path / "videos"
    videos_dir.mkdir()

    db_path = str(data_dir / "db" / "test.db")

    # Point config paths to the temp directory
    monkeypatch.setenv("DB_PATH", db_path)
    monkeypatch.setenv("CHROMA_PATH", str(data_dir / "chroma"))

    # Change working directory so relative paths resolve inside tmp
    monkeypatch.chdir(tmp_path)

    # Create config.yaml in the tmp dir with supported_extensions
    config_yaml = tmp_path / "config.yaml"
    config_yaml.write_text(
        'ingestion:\n'
        '  max_upload_bytes: 2147483648\n'
        '  supported_extensions: [".mp4", ".webm", ".mkv", ".mov", ".avi", ".mp3", ".wav", ".m4a"]\n'
        'ollama_url: http://localhost:11434\n'
        'model_names:\n'
        '  embedding: bge-m3:latest\n'
        '  llm: llama3.2\n'
    )

    # Create migration directory structure expected by run_migrations
    migrations_dir = tmp_path / "db" / "migrations"
    migrations_dir.mkdir(parents=True)
    # Copy actual migration files
    real_migrations = Path(__file__).resolve().parents[2] / "db" / "migrations"
    for sql_file in sorted(real_migrations.glob("*.sql")):
        shutil.copy(sql_file, migrations_dir / sql_file.name)

    # Force config reload with new env vars and new cwd (config.yaml)
    import videoqa.config
    new_config = videoqa.config.load_config()
    monkeypatch.setattr(videoqa.config, "config", new_config)

    # Re-run migrations to create tables in the temp DB
    from videoqa.db.sqlite import run_migrations
    run_migrations()

    yield tmp_path


@pytest.fixture
def client(monkeypatch):
    """Create a fresh FastAPI TestClient (without triggering run_migrations again)."""
    from videoqa.main import app
    import videoqa.api.ingest as ingest_api
    monkeypatch.setattr(ingest_api, "ingest_file", lambda *args, **kwargs: None)
    return TestClient(app, raise_server_exceptions=False)


@lru_cache(maxsize=4)
def _make_test_video_bytes(size: int = 1024, extension: str = ".mp4") -> bytes:
    """Create a short real video with FFmpeg for deterministic integration tests."""
    import shutil
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        pytest.skip("FFmpeg is required to create deterministic upload fixtures")
    with tempfile.TemporaryDirectory() as directory:
        output = Path(directory) / f"sample{extension}"
        command = [
            ffmpeg, "-hide_banner", "-loglevel", "error", "-y",
            "-f", "lavfi", "-i", "testsrc2=size=160x90:rate=30:duration=3",
            "-an",
        ]
        if extension == ".webm":
            command += ["-c:v", "libvpx-vp9", "-deadline", "realtime", "-cpu-used", "8", "-crf", "35", "-b:v", "0"]
        else:
            # H.264/yuv420p is broadly supported by browsers; MPEG-4 Part 2
            # files can be valid MP4 containers but fail in HTMLVideoElement.
            command += ["-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", "-movflags", "+faststart"]
        command.append(str(output))
        subprocess.run(command, check=True, capture_output=True)
        return output.read_bytes()


# ---------------------------------------------------------------------------
# Upload & Persistence Tests
# ---------------------------------------------------------------------------

class TestUploadPersistence:
    """Tests for the /api/ingest/file endpoint and DB persistence."""

    def test_upload_valid_mp4(self, client, _isolated_data_dir):
        """Upload a valid .mp4 file and verify DB record creation."""
        content = _make_test_video_bytes(4096)
        response = client.post(
            "/api/ingest/file",
            files={"file": ("test_video.mp4", io.BytesIO(content), "video/mp4")},
        )
        assert response.status_code == 202, response.text
        data = response.json()
        assert "video_id" in data
        assert "job_id" in data
        assert data["status"] == "queued"

        # Verify the file exists on disk
        video_id = data["video_id"]
        media_dir = _isolated_data_dir / "data" / "media"
        files_on_disk = list(media_dir.glob(f"{video_id}*"))
        assert len(files_on_disk) == 1
        assert files_on_disk[0].stat().st_size == len(content)

    def test_upload_valid_webm(self, client, _isolated_data_dir):
        """Upload a valid .webm file."""
        content = _make_test_video_bytes(2048, ".webm")
        response = client.post(
            "/api/ingest/file",
            files={"file": ("lecture.webm", io.BytesIO(content), "video/webm")},
        )
        assert response.status_code == 202, response.text

    def test_upload_unsupported_extension(self, client):
        """Reject a file with an unsupported extension."""
        response = client.post(
            "/api/ingest/file",
            files={"file": ("malicious.exe", io.BytesIO(b"MZ"), "application/octet-stream")},
        )
        assert response.status_code == 422
        assert "Unsupported file type" in response.json()["detail"]

    def test_upload_malformed_media_returns_validation_error(self, client, _isolated_data_dir):
        response = client.post(
            "/api/ingest/file",
            files={"file": ("not-a-video.mp4", io.BytesIO(b"not an mp4"), "video/mp4")},
        )
        assert response.status_code == 422
        assert "signature does not match" in response.json()["detail"]
        assert list((_isolated_data_dir / "data" / "media").iterdir()) == []

    def test_upload_creates_db_record(self, client):
        """After upload, the video appears in the database."""
        content = _make_test_video_bytes(1024)
        resp = client.post(
            "/api/ingest/file",
            files={"file": ("db_test.mp4", io.BytesIO(content), "video/mp4")},
        )
        assert resp.status_code == 202
        video_id = resp.json()["video_id"]

        # Query the video detail endpoint
        detail = client.get(f"/api/videos/{video_id}")
        assert detail.status_code == 200
        video = detail.json()
        assert video["video_id"] == video_id
        assert video["source_type"] == "file_upload"
        assert video["media_available"] is True
        assert "file_path" not in video
        assert video["status"] == "queued"

    def test_upload_appears_in_library(self, client):
        """After upload, the video appears in the library listing."""
        content = _make_test_video_bytes(1024)
        resp = client.post(
            "/api/ingest/file",
            files={"file": ("library_test.mp4", io.BytesIO(content), "video/mp4")},
        )
        assert resp.status_code == 202
        video_id = resp.json()["video_id"]

        lib = client.get("/api/videos")
        assert lib.status_code == 200
        videos = lib.json()["videos"]
        ids = [v["video_id"] for v in videos]
        assert video_id in ids

    def test_db_record_persists_across_requests(self, client):
        """The record remains after upload (no rollback)."""
        content = _make_test_video_bytes(512)
        resp = client.post(
            "/api/ingest/file",
            files={"file": ("persist.mp4", io.BytesIO(content), "video/mp4")},
        )
        assert resp.status_code == 202
        video_id = resp.json()["video_id"]

        # Fetch again in a new request
        detail = client.get(f"/api/videos/{video_id}")
        assert detail.status_code == 200
        assert detail.json()["video_id"] == video_id

    def test_upload_has_media_url(self, client):
        """The API response includes a media_url when file_path is set."""
        content = _make_test_video_bytes(1024)
        resp = client.post(
            "/api/ingest/file",
            files={"file": ("media_url_test.mp4", io.BytesIO(content), "video/mp4")},
        )
        assert resp.status_code == 202
        video_id = resp.json()["video_id"]

        detail = client.get(f"/api/videos/{video_id}")
        video = detail.json()
        assert video.get("media_url") == f"/api/videos/{video_id}/media"

    def test_same_source_upload_is_deduplicated(self, client, _isolated_data_dir):
        content = _make_test_video_bytes()
        first = client.post("/api/ingest/file", files={"file": ("same.mp4", io.BytesIO(content), "video/mp4")})
        second = client.post("/api/ingest/file", files={"file": ("same.mp4", io.BytesIO(content), "video/mp4")})
        assert first.status_code == 202
        assert second.status_code == 200
        assert second.json()["video_id"] == first.json()["video_id"]
        assert len(list((_isolated_data_dir / "data" / "media").glob("*.mp4"))) == 1

    def test_database_failure_cleans_up_stored_upload(self, client, _isolated_data_dir, monkeypatch):
        import videoqa.api.ingest as ingest_api
        monkeypatch.setattr(ingest_api, "create_queued_file_video", lambda *args: (_ for _ in ()).throw(RuntimeError("db unavailable")))
        response = client.post("/api/ingest/file", files={"file": ("db-failure.mp4", io.BytesIO(_make_test_video_bytes()), "video/mp4")})
        assert response.status_code == 500
        assert list((_isolated_data_dir / "data" / "media").iterdir()) == []
        assert client.get("/api/videos").json()["total"] == 0

    def test_unavailable_media_directory_returns_clear_error(self, client, _isolated_data_dir, monkeypatch):
        import videoqa.api.ingest as ingest_api
        blocker = _isolated_data_dir / "media-root-is-a-file"
        blocker.write_text("not a directory", encoding="utf-8")
        monkeypatch.setattr(ingest_api, "media_root", lambda: blocker)
        response = client.post(
            "/api/ingest/file",
            files={"file": ("storage-error.mp4", io.BytesIO(_make_test_video_bytes()), "video/mp4")},
        )
        assert response.status_code == 503
        assert response.json()["detail"] == "Media storage is unavailable."
        assert list((_isolated_data_dir / "data" / "media").iterdir()) == []
        assert client.get("/api/videos").json()["total"] == 0

    def test_interrupted_upload_removes_temporary_file(self, _isolated_data_dir):
        import asyncio
        from fastapi import BackgroundTasks, Response
        import videoqa.api.ingest as ingest_api

        class InterruptedUpload:
            filename = "interrupted.mp4"
            content_type = "video/mp4"

            async def read(self, _size=-1):
                raise asyncio.CancelledError()

            async def close(self):
                return None

        with pytest.raises(asyncio.CancelledError):
            asyncio.run(ingest_api.ingest_file_endpoint(BackgroundTasks(), Response(), InterruptedUpload()))

        media_dir = _isolated_data_dir / "data" / "media"
        assert list(media_dir.iterdir()) == []
        assert not list(media_dir.glob(".upload-*"))

    def test_failed_transcription_keeps_source_playable_and_retry_is_serialized(self, client, monkeypatch):
        from videoqa.core import ingestion
        from videoqa.db.sqlite import get_video
        from videoqa.storage import resolve_media_path
        import videoqa.api.jobs as jobs_api

        content = _make_test_video_bytes()
        upload = client.post("/api/ingest/file", files={"file": ("failure.mp4", io.BytesIO(content), "video/mp4")})
        assert upload.status_code == 202
        video_id = upload.json()["video_id"]
        record = get_video(video_id)
        source = resolve_media_path(record["file_path"])
        assert source and source.is_file()

        def fail_transcription(*args, **kwargs):
            raise RuntimeError("faster-whisper model unavailable")

        monkeypatch.setattr(ingestion, "transcribe_audio", fail_transcription)
        result = ingestion.ingest_file(str(source), video_id, record["title"])
        assert result["status"] == "failed"
        failed_record = get_video(video_id)
        assert failed_record["status"] == "failed"
        assert failed_record["error_message"] == "transcribing: faster-whisper model unavailable"
        assert source.is_file()
        playback = client.get(f"/api/videos/{video_id}/media")
        assert playback.status_code == 200
        assert playback.content == content

        monkeypatch.setattr(ingestion, "delete_video_chroma", lambda _video_id: None)
        monkeypatch.setattr(jobs_api, "ingest_file", lambda *args, **kwargs: None)
        first_retry = client.post(f"/api/jobs/{video_id}/retry")
        second_retry = client.post(f"/api/jobs/{video_id}/retry")
        assert first_retry.status_code == 200
        assert first_retry.json()["video_id"] == video_id
        assert first_retry.json()["retry_count"] == 1
        assert second_retry.status_code == 409
        retried_record = get_video(video_id)
        assert retried_record["file_path"] == failed_record["file_path"]
        assert source.is_file()


class TestDatabasePathRegression:
    def _record(self, tmp_path):
        from datetime import datetime, timezone
        from videoqa.db.sqlite import upsert_video
        from videoqa.storage import media_reference

        source = tmp_path / "data" / "media" / "record.webm"
        source.parent.mkdir(parents=True, exist_ok=True)
        source.write_bytes(bytes.fromhex("1A45DFA3") + b"readable")
        now = datetime.now(timezone.utc).isoformat()
        record = {
            "id": str(uuid.uuid4()),
            "video_id": "status-path-test",
            "source_type": "file_upload",
            "title": "Status path test",
            "duration_seconds": 1,
            "file_path": media_reference(source),
            "status": "queued",
            "created_at": now,
            "updated_at": now,
        }
        upsert_video(record)
        return record, source

    def test_path_survives_status_transitions_and_retry(self, client, _isolated_data_dir):
        from datetime import datetime, timezone
        from videoqa.db.sqlite import claim_video_retry, get_video, update_video_status

        record, _ = self._record(_isolated_data_dir)
        expected = record["file_path"]
        for state in ("downloading", "transcribing", "chunking", "embedding", "ready", "failed"):
            assert update_video_status(record["video_id"], state, datetime.now(timezone.utc).isoformat())
            assert get_video(record["video_id"])["file_path"] == expected
        retried = claim_video_retry(record["video_id"], datetime.now(timezone.utc).isoformat())
        assert retried and retried["status"] == "queued"
        assert retried["retry_count"] == 1
        assert get_video(record["video_id"])["file_path"] == expected

    def test_null_path_upsert_preserves_path_and_explicit_update_works(self, client, _isolated_data_dir):
        from datetime import datetime, timezone
        from videoqa.db.sqlite import get_video, upsert_video
        from videoqa.storage import media_reference

        record, _ = self._record(_isolated_data_dir)
        upsert_video({**record, "file_path": None, "status": "failed"})
        assert get_video(record["video_id"])["file_path"] == record["file_path"]

        replacement = _isolated_data_dir / "data" / "media" / "replacement.webm"
        replacement.write_bytes(bytes.fromhex("1A45DFA3") + b"replacement")
        upsert_video({**get_video(record["video_id"]), "file_path": media_reference(replacement), "updated_at": datetime.now(timezone.utc).isoformat()})
        assert get_video(record["video_id"])["file_path"] == media_reference(replacement)

    def test_failed_status_write_rolls_back_without_touching_media_path(self, client, _isolated_data_dir):
        from datetime import datetime, timezone
        from videoqa.db.sqlite import get_video, update_video_status

        record, _ = self._record(_isolated_data_dir)
        with pytest.raises(sqlite3.IntegrityError):
            update_video_status(record["video_id"], None, datetime.now(timezone.utc).isoformat())
        assert get_video(record["video_id"])["file_path"] == record["file_path"]
        assert get_video(record["video_id"])["status"] == "queued"

    def test_no_filename_rejected(self, client):
        """Upload without a filename is rejected."""
        response = client.post(
            "/api/ingest/file",
            files={"file": ("", io.BytesIO(b""), "video/mp4")},
        )
        assert response.status_code == 422


# ---------------------------------------------------------------------------
# Playback / Media Endpoint Tests
# ---------------------------------------------------------------------------

class TestMediaPlayback:
    """Tests for GET /api/videos/{video_id}/media."""

    def _create_video_with_file(self, client, tmp_path, filename="test.mp4", content=None):
        """Upload a video and return its video_id."""
        if content is None:
            content = _make_test_video_bytes(4096)
        resp = client.post(
            "/api/ingest/file",
            files={"file": (filename, io.BytesIO(content), "video/mp4")},
        )
        assert resp.status_code == 202, resp.text
        return resp.json()["video_id"], content

    def test_media_endpoint_returns_file(self, client, _isolated_data_dir):
        """GET /api/videos/{id}/media returns the file content."""
        video_id, content = self._create_video_with_file(client, _isolated_data_dir)
        resp = client.get(f"/api/videos/{video_id}/media")
        assert resp.status_code == 200
        assert resp.content == content

    def test_head_returns_media_headers_without_body(self, client, _isolated_data_dir):
        video_id, content = self._create_video_with_file(client, _isolated_data_dir)
        response = client.head(f"/api/videos/{video_id}/media")
        assert response.status_code == 200
        assert response.headers["content-length"] == str(len(content))
        assert response.headers["accept-ranges"] == "bytes"
        assert response.content == b""

    def test_media_content_type(self, client, _isolated_data_dir):
        """Media endpoint returns the correct MIME type."""
        video_id, _ = self._create_video_with_file(client, _isolated_data_dir)
        resp = client.get(f"/api/videos/{video_id}/media")
        assert "video/mp4" in resp.headers.get("content-type", "")

    def test_media_inline_disposition(self, client, _isolated_data_dir):
        """Media is served inline, not as a download."""
        video_id, _ = self._create_video_with_file(client, _isolated_data_dir)
        resp = client.get(f"/api/videos/{video_id}/media")
        content_disp = resp.headers.get("content-disposition", "")
        # Either inline or absent is acceptable
        assert "attachment" not in content_disp

    def test_media_range_request(self, client, _isolated_data_dir):
        """A Range request returns 206 Partial Content."""
        content = _make_test_video_bytes(8192)
        video_id, _ = self._create_video_with_file(
            client, _isolated_data_dir, content=content
        )
        resp = client.get(
            f"/api/videos/{video_id}/media",
            headers={"Range": "bytes=0-1023"},
        )
        assert resp.status_code == 206
        assert resp.headers.get("content-range", "").startswith("bytes 0-1023/")
        assert len(resp.content) == 1024

    def test_media_seek_later_portion(self, client, _isolated_data_dir):
        """Seeking to a later portion returns the correct bytes."""
        content = _make_test_video_bytes(8192)
        video_id, _ = self._create_video_with_file(
            client, _isolated_data_dir, content=content
        )
        resp = client.get(
            f"/api/videos/{video_id}/media",
            headers={"Range": "bytes=4096-8191"},
        )
        assert resp.status_code == 206
        assert resp.content == content[4096:8192]

    def test_invalid_range_returns_416(self, client, _isolated_data_dir):
        video_id, content = self._create_video_with_file(client, _isolated_data_dir)
        response = client.get(f"/api/videos/{video_id}/media", headers={"Range": f"bytes={len(content)}-"})
        assert response.status_code == 416
        assert response.headers["content-range"] == f"bytes */{len(content)}"

    def test_media_missing_file_returns_404(self, client, _isolated_data_dir):
        """If the file is deleted from disk, 404 is returned."""
        video_id, _ = self._create_video_with_file(client, _isolated_data_dir)
        # Delete the file from disk
        media_dir = _isolated_data_dir / "data" / "media"
        for f in media_dir.glob(f"{video_id}*"):
            f.unlink()

        resp = client.get(f"/api/videos/{video_id}/media")
        assert resp.status_code == 404

    def test_media_unknown_id_returns_404(self, client):
        """An unknown video ID returns 404."""
        resp = client.get("/api/videos/nonexistent-id/media")
        assert resp.status_code == 404

    def test_path_traversal_blocked(self, client):
        """Arbitrary filesystem paths cannot be accessed via the media endpoint."""
        from videoqa.db.sqlite import upsert_video
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc).isoformat()
        upsert_video({
            "id": str(uuid.uuid4()),
            "video_id": "traversal-test",
            "source_type": "file_upload",
            "title": "Traversal Test",
            "file_path": "../../etc/passwd",
            "status": "ready",
            "duration_seconds": 0,
            "created_at": now,
            "updated_at": now,
        })
        resp = client.get("/api/videos/traversal-test/media")
        # Should be 403 or 404, never 200
        assert resp.status_code in (403, 404)

    def test_media_from_videos_directory(self, client, _isolated_data_dir):
        """Videos stored in the videos/ directory can be served."""
        from videoqa.db.sqlite import upsert_video
        from datetime import datetime, timezone

        # Create a test file in videos/
        videos_dir = _isolated_data_dir / "videos"
        test_file = videos_dir / "legacy_video.webm"
        content = _make_test_video_bytes(2048, ".webm")
        test_file.write_bytes(content)

        now = datetime.now(timezone.utc).isoformat()
        upsert_video({
            "id": str(uuid.uuid4()),
            "video_id": "legacy-test",
            "source_type": "file_upload",
            "title": "Legacy Test",
            "file_path": str(test_file),
            "status": "ready",
            "duration_seconds": 60,
            "created_at": now,
            "updated_at": now,
        })

        resp = client.get("/api/videos/legacy-test/media")
        assert resp.status_code == 200
        assert resp.content == content
        assert "video/webm" in resp.headers.get("content-type", "")


# ---------------------------------------------------------------------------
# API Contract Tests
# ---------------------------------------------------------------------------

class TestAPIContracts:
    """Verify frontend-backend API contract alignment."""

    def test_video_list_shape(self, client):
        """GET /api/videos returns {videos: [...], total: N}."""
        resp = client.get("/api/videos")
        assert resp.status_code == 200
        data = resp.json()
        assert "videos" in data
        assert "total" in data
        assert isinstance(data["videos"], list)

    def test_upload_response_shape(self, client):
        """POST /api/ingest/file returns the expected JobStart fields."""
        content = _make_test_video_bytes()
        resp = client.post(
            "/api/ingest/file",
            files={"file": ("shape_test.mp4", io.BytesIO(content), "video/mp4")},
        )
        assert resp.status_code == 202
        data = resp.json()
        assert "job_id" in data
        assert "video_id" in data
        assert "status" in data

    def test_health_endpoint(self, client):
        """GET /api/health returns status info."""
        resp = client.get("/api/health")
        assert resp.status_code == 200
        data = resp.json()
        assert "status" in data
        assert {"api", "sqlite", "chroma", "media_storage", "ffmpeg", "ffprobe", "faster_whisper", "ollama", "ollama_models"}.issubset(data["services"])

    def test_video_detail_includes_media_url(self, client):
        """Video detail response includes media_url when file_path exists."""
        content = _make_test_video_bytes()
        resp = client.post(
            "/api/ingest/file",
            files={"file": ("contract.mp4", io.BytesIO(content), "video/mp4")},
        )
        assert resp.status_code == 202
        vid = resp.json()["video_id"]
        detail = client.get(f"/api/videos/{vid}")
        assert detail.status_code == 200
        assert "media_url" in detail.json()

    def test_upload_multipart_field_name(self, client):
        """The upload uses 'file' as the multipart field name."""
        # Using wrong field name should fail
        content = _make_test_video_bytes()
        resp = client.post(
            "/api/ingest/file",
            files={"wrong_name": ("test.mp4", io.BytesIO(content), "video/mp4")},
        )
        assert resp.status_code == 422
        assert resp.json()["detail"][0]["loc"] == ["body", "file"]


# ---------------------------------------------------------------------------
# Delete Tests
# ---------------------------------------------------------------------------

class TestDelete:
    """Tests for video deletion."""

    def test_delete_removes_from_library(self, client):
        """Deleting a video removes it from the library list."""
        content = _make_test_video_bytes()
        resp = client.post(
            "/api/ingest/file",
            files={"file": ("delete_test.mp4", io.BytesIO(content), "video/mp4")},
        )
        assert resp.status_code == 202
        video_id = resp.json()["video_id"]

        # Delete
        del_resp = client.delete(f"/api/videos/{video_id}")
        assert del_resp.status_code == 200
        assert del_resp.json()["deleted"] is True

        # Verify it's gone
        lib = client.get("/api/videos")
        ids = [v["video_id"] for v in lib.json()["videos"]]
        assert video_id not in ids

    def test_delete_nonexistent_returns_404(self, client):
        """Deleting a non-existent video returns 404."""
        resp = client.delete("/api/videos/does-not-exist")
        assert resp.status_code == 404
