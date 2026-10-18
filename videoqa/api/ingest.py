from fastapi import APIRouter, BackgroundTasks, HTTPException, UploadFile, File, Response, status
from pydantic import BaseModel
from videoqa.core.ingestion import ingest_url, ingest_file, make_queued_url_video, create_queued_file_video
import videoqa.config as config_module
from videoqa.db.sqlite import get_video, update_video_file_path
from videoqa.storage import media_file_is_readable, media_reference, media_root, resolve_media_path
import hashlib
import json
import logging
import os
import re
import shutil
import subprocess
import tempfile
import uuid
from pathlib import Path
from urllib.parse import urlparse
from datetime import datetime, timezone

router = APIRouter(prefix="/api/ingest", tags=["ingest"])
logger = logging.getLogger(__name__)

class IngestUrlRequest(BaseModel):
    url: str


MIME_TYPES = {
    ".mp4": {"video/mp4"},
    ".webm": {"video/webm", "audio/webm"},
    ".mkv": {"video/x-matroska", "application/x-matroska"},
    ".mov": {"video/quicktime"},
    ".avi": {"video/x-msvideo", "video/avi"},
    ".mp3": {"audio/mpeg", "audio/mp3"},
    ".wav": {"audio/wav", "audio/x-wav", "audio/wave"},
    ".m4a": {"audio/mp4", "audio/x-m4a"},
}


def _safe_display_filename(filename: str) -> str:
    basename = Path(filename.replace("\\", "/")).name
    cleaned = re.sub(r'[\x00-\x1f<>:"|?*]', "_", basename).strip(" .")
    return cleaned[:240] or "uploaded-media"


def _validate_signature(path: Path, extension: str) -> None:
    with path.open("rb") as source:
        header = source.read(16)
    valid = False
    if extension in {".mp4", ".mov", ".m4a"}:
        valid = len(header) >= 8 and header[4:8] == b"ftyp"
    elif extension in {".webm", ".mkv"}:
        valid = header.startswith(bytes.fromhex("1A45DFA3"))
    elif extension == ".avi":
        valid = len(header) >= 12 and header[:4] == b"RIFF" and header[8:12] == b"AVI "
    elif extension == ".mp3":
        valid = header.startswith(b"ID3") or (len(header) >= 2 and header[0] == 0xFF and header[1] & 0xE0 == 0xE0)
    elif extension == ".wav":
        valid = len(header) >= 12 and header[:4] == b"RIFF" and header[8:12] == b"WAVE"
    if not valid:
        raise HTTPException(status_code=422, detail="The uploaded file signature does not match its extension.")


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _inspect_upload(path: Path, extension: str, content_type: str | None) -> float:
    declared_type = (content_type or "").split(";", 1)[0].strip().lower()
    supported_mimes = MIME_TYPES.get(extension, set())
    if declared_type and declared_type != "application/octet-stream" and declared_type not in supported_mimes:
        raise HTTPException(status_code=422, detail="The uploaded media type does not match its file extension.")

    _validate_signature(path, extension)
    ffprobe = shutil.which("ffprobe")
    if not ffprobe:
        raise HTTPException(status_code=503, detail="Media validation is unavailable because ffprobe is not installed.")
    try:
        result = subprocess.run(
            [ffprobe, "-v", "error", "-show_entries", "format=duration:stream=codec_type", "-of", "json", str(path)],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise HTTPException(status_code=422, detail="The uploaded file could not be validated before the time limit.") from exc
    if result.returncode != 0:
        raise HTTPException(status_code=422, detail="The uploaded file is not a readable media file.")
    try:
        metadata = json.loads(result.stdout)
        duration = float(metadata.get("format", {}).get("duration", 0))
        stream_types = {stream.get("codec_type") for stream in metadata.get("streams", [])}
    except (ValueError, TypeError, json.JSONDecodeError):
        raise HTTPException(status_code=422, detail="The uploaded file has invalid media metadata.")
    if not stream_types or not stream_types.intersection({"audio", "video"}) or duration <= 0:
        raise HTTPException(status_code=422, detail="The uploaded file has no readable audio or video stream.")
    if extension in {".mp4", ".webm", ".mkv", ".mov", ".avi"} and "video" not in stream_types:
        raise HTTPException(status_code=422, detail="This video file does not contain a video stream.")
    if extension in {".mp3", ".wav", ".m4a"} and "audio" not in stream_types:
        raise HTTPException(status_code=422, detail="This audio file does not contain an audio stream.")

    max_duration = float(config_module.config.get("ingestion", {}).get("max_duration_seconds", 4 * 60 * 60))
    if duration > max_duration:
        raise HTTPException(status_code=422, detail=f"The media duration exceeds the {int(max_duration // 60)} minute limit.")
    return duration


def job_response(video: dict, status: str | None = None, message: str | None = None) -> dict:
    response = {
        "job_id": video['video_id'],
        "video_id": video['video_id'],
        "title": video.get('title'),
        "duration_seconds": video.get('duration_seconds', 0),
        "thumbnail_url": video.get('thumbnail_url'),
        "status": status or video.get('status', 'queued'),
    }
    if message:
        response['message'] = message
    return response

@router.post("/url", status_code=status.HTTP_202_ACCEPTED)
def ingest_url_endpoint(req: IngestUrlRequest, background_tasks: BackgroundTasks, response: Response):
    url = req.url.strip()
    parsed = urlparse(url)
    if parsed.scheme not in {'http', 'https'} or not parsed.netloc:
        raise HTTPException(status_code=422, detail="Enter a valid http(s) video URL.")

    video, already_indexed = make_queued_url_video(url)
    if already_indexed:
        response.status_code = status.HTTP_200_OK
        return job_response(video, "already_indexed", "This video is already in your library.")
    if video.get('status') not in {'queued', 'failed', 'cancelled'}:
        response.status_code = status.HTTP_200_OK
        return job_response(video, video['status'], "This video is already being processed.")

    background_tasks.add_task(ingest_url, url, video['video_id'])
    return job_response(video, "queued", "Ingestion started in the background.")

@router.post("/file", status_code=status.HTTP_202_ACCEPTED)
async def ingest_file_endpoint(background_tasks: BackgroundTasks, response: Response, file: UploadFile = File(...)):
    if not file.filename:
        raise HTTPException(status_code=422, detail="Choose a video or audio file to upload.")

    original_filename = _safe_display_filename(file.filename)
    extension = Path(original_filename).suffix.lower()
    ingestion_config = config_module.config.get('ingestion', {})
    allowed_extensions = set(ingestion_config.get('supported_extensions', []))
    max_upload_bytes = int(ingestion_config.get('max_upload_bytes', 2 * 1024 * 1024 * 1024))
    if extension not in allowed_extensions:
        supported = ', '.join(sorted(allowed_extensions))
        raise HTTPException(status_code=422, detail=f"Unsupported file type. Supported formats: {supported}.")

    storage_dir = media_root()
    try:
        storage_dir.mkdir(parents=True, exist_ok=True)
        descriptor, temporary_name = tempfile.mkstemp(prefix=".upload-", suffix=extension, dir=storage_dir)
    except OSError as exc:
        await file.close()
        raise HTTPException(status_code=503, detail="Media storage is unavailable.") from exc
    temporary_path = Path(temporary_name)
    received_bytes = 0
    digest = hashlib.sha256()
    created_final_path: Path | None = None
    record_committed = False

    try:
        with os.fdopen(descriptor, "wb") as destination:
            while chunk := await file.read(1024 * 1024):
                received_bytes += len(chunk)
                if received_bytes > max_upload_bytes:
                    raise HTTPException(status_code=413, detail="This file exceeds the configured upload limit.")
                destination.write(chunk)
                digest.update(chunk)
            destination.flush()
            os.fsync(destination.fileno())
        if received_bytes == 0:
            raise HTTPException(status_code=422, detail="The uploaded file is empty.")

        duration = _inspect_upload(temporary_path, extension, file.content_type)
        content_digest = digest.hexdigest()
        video_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"videoqa-upload:{content_digest}"))
        final_path = storage_dir / f"{video_id}{extension}"
        reference = media_reference(final_path, "media")

        existing = get_video(video_id)
        if existing:
            if existing.get("source_type") != "file_upload":
                raise HTTPException(status_code=409, detail="This file ID is already used by another video source.")
            existing_path = resolve_media_path(existing.get("file_path")) if existing.get("file_path") else None
            if existing_path and media_file_is_readable(existing_path):
                existing_digest = _sha256_file(existing_path)
                if existing_digest != content_digest:
                    raise HTTPException(status_code=409, detail="A different file already uses this video ID.")
                temporary_path.unlink()
                response.status_code = status.HTTP_200_OK
                return job_response(existing, existing.get("status"), "This exact file is already in your library.")

            if final_path.exists():
                if _sha256_file(final_path) != content_digest:
                    raise HTTPException(status_code=409, detail="A different file already exists at this storage key.")
                temporary_path.unlink()
            else:
                os.replace(temporary_path, final_path)
                created_final_path = final_path
            if not media_file_is_readable(final_path):
                raise HTTPException(status_code=500, detail="The uploaded file could not be verified in storage.")
            update_video_file_path(video_id, reference, datetime.now(timezone.utc).isoformat())
            record_committed = True
            existing["file_path"] = reference
            response.status_code = status.HTTP_200_OK
            return job_response(existing, existing.get("status"), "The stored media file has been restored.")

        if final_path.exists():
            if _sha256_file(final_path) != content_digest:
                raise HTTPException(status_code=409, detail="A different file already exists at this storage key.")
            temporary_path.unlink()
        else:
            os.replace(temporary_path, final_path)
            created_final_path = final_path
        if not media_file_is_readable(final_path):
            raise HTTPException(status_code=500, detail="The uploaded file could not be verified in storage.")
        video, created = create_queued_file_video(reference, video_id, original_filename, duration)
        if not created:
            current_path = resolve_media_path(video.get("file_path")) if video and video.get("file_path") else None
            if not current_path or not media_file_is_readable(current_path):
                update_video_file_path(video_id, reference, datetime.now(timezone.utc).isoformat())
                record_committed = True
                video = get_video(video_id)
            else:
                record_committed = True
            response.status_code = status.HTTP_200_OK
            return job_response(video, video.get("status") if video else "queued", "This exact file is already in your library.")
        record_committed = True
        background_tasks.add_task(ingest_file, str(final_path), video_id, original_filename)
        return job_response(video, "queued", "Upload complete. Processing has started.")
    except HTTPException:
        if temporary_path.exists():
            temporary_path.unlink()
        if not record_committed and created_final_path and created_final_path.exists():
            created_final_path.unlink()
        raise
    except Exception as exc:
        if temporary_path.exists():
            temporary_path.unlink()
        if not record_committed and created_final_path and created_final_path.exists():
            created_final_path.unlink()
        raise HTTPException(status_code=500, detail="Unable to save the uploaded file and its metadata.") from exc
    finally:
        try:
            await file.close()
        finally:
            # Cancellation (for example, a disconnected browser) bypasses
            # ``except Exception`` on modern Python. Remove only this request's
            # temporary file and any final file it created before DB commit.
            cleanup_paths = [temporary_path]
            if not record_committed and created_final_path is not None:
                cleanup_paths.append(created_final_path)
            for cleanup_path in cleanup_paths:
                try:
                    cleanup_path.unlink(missing_ok=True)
                except OSError:
                    logger.warning("Could not clean up an incomplete upload file")
