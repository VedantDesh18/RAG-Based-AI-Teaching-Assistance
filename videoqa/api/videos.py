import logging
import mimetypes
from fastapi import APIRouter, BackgroundTasks, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel
from videoqa.db.sqlite import delete_video_sqlite, get_video, get_transcript_segments, list_videos as list_video_records
from videoqa.vectorstore.chroma import delete_video_chroma
from videoqa.core.ingestion import ingest_file, ingest_url, reset_for_reprocess
from pathlib import Path
from videoqa.storage import media_file_is_readable, media_root, resolve_media_path

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/videos", tags=["videos"])


class ReprocessRequest(BaseModel):
    language: str | None = None

def _add_media_url(video: dict) -> dict:
    """Expose playback availability without returning local filesystem paths."""
    if not video:
        return video
    source_type = video.get("source_type")
    media_path = resolve_media_path(video["file_path"]) if video.get("file_path") else None
    media_available = source_type == "youtube" or bool(media_path and media_file_is_readable(media_path))
    video["media_available"] = media_available
    video.pop("file_path", None)
    if source_type != "youtube" and media_available:
        video["media_url"] = f"/api/videos/{video['video_id']}/media"
    return video


@router.get("")
def list_videos():
    videos = list_video_records()
    for v in videos:
        _add_media_url(v)
    return {"videos": videos, "total": len(videos)}


@router.get("/{video_id}")
def get_video_detail(video_id: str):
    video = get_video(video_id)
    if not video:
        raise HTTPException(status_code=404, detail="Video not found")
    return _add_media_url(video)


@router.get("/{video_id}/transcript")
def get_transcript(video_id: str):
    if not get_video(video_id):
        raise HTTPException(status_code=404, detail="Video not found")
    segments = get_transcript_segments(video_id)
    return {"video_id": video_id, "segments": segments, "total": len(segments)}

@router.delete("/{video_id}")
def delete_video(video_id: str):
    video = get_video(video_id)
    if not video:
        raise HTTPException(status_code=404, detail="Video not found")
    # Delete from chroma
    delete_video_chroma(video_id)
    # Delete from sqlite
    chunks_removed = delete_video_sqlite(video_id)

    # Uploaded files are owned by the application. Shared legacy files remain in place.
    media_path = resolve_media_path(video.get("file_path")) if video.get("file_path") else None
    if media_path and media_path.is_relative_to(media_root()) and media_path.is_file():
        media_path.unlink()

    return {"deleted": True, "video_id": video_id, "chunks_removed": chunks_removed}


@router.post("/{video_id}/reprocess")
def reprocess_video_endpoint(
    video_id: str,
    background_tasks: BackgroundTasks,
    req: ReprocessRequest = ReprocessRequest(),
):
    """
    Safely reprocess/retranscribe an existing video with an optional explicit language
    (e.g. language="hi" for Hindi in Devanagari script) without deleting the original video file.
    """
    video = get_video(video_id)
    if not video:
        raise HTTPException(status_code=404, detail="Video not found")
    try:
        video = reset_for_reprocess(video_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if video.get('source_type') == 'file_upload':
        source_path = resolve_media_path(video.get('file_path'))
        background_tasks.add_task(ingest_file, str(source_path), video_id, video['title'], req.language)
    else:
        background_tasks.add_task(ingest_url, video['source_url'], video_id, req.language)

    return {
        "job_id": video_id,
        "video_id": video_id,
        "status": "queued",
        "language": req.language,
        "message": f"Reprocessing started for video {video_id} with language: {req.language or 'auto'}.",
    }



def _video_media_response(video_id: str):
    video = get_video(video_id)
    if not video or not video.get('file_path'):
        raise HTTPException(status_code=404, detail="Media not found")

    abs_file_path = resolve_media_path(video["file_path"])
    if abs_file_path is None:
        logger.warning("Blocked media path for video %s", video_id)
        raise HTTPException(status_code=403, detail="Forbidden")

    if not media_file_is_readable(abs_file_path):
        logger.warning("Media file is missing or unreadable for video %s", video_id)
        raise HTTPException(status_code=404, detail="File missing from disk")

    # Determine MIME type from the extension
    media_type, _ = mimetypes.guess_type(str(abs_file_path))
    if not media_type:
        media_type = "application/octet-stream"

    # Starlette FileResponse handles Range / 206 Partial Content automatically.
    return FileResponse(
        path=abs_file_path,
        media_type=media_type,
        content_disposition_type="inline",  # stream in browser, don't download
    )


@router.get("/{video_id}/media")
def get_video_media(video_id: str):
    return _video_media_response(video_id)


@router.head("/{video_id}/media", include_in_schema=False)
def head_video_media(video_id: str):
    return _video_media_response(video_id)

