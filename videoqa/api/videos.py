from fastapi import APIRouter, HTTPException
from videoqa.db.sqlite import delete_video_sqlite, get_video, get_transcript_segments, list_videos as list_video_records
from videoqa.vectorstore.chroma import delete_video_chroma
import os
from pathlib import Path

router = APIRouter(prefix="/api/videos", tags=["videos"])

@router.get("")
def list_videos():
    videos = list_video_records()
    return {"videos": videos, "total": len(videos)}


@router.get("/{video_id}")
def get_video_detail(video_id: str):
    video = get_video(video_id)
    if not video:
        raise HTTPException(status_code=404, detail="Video not found")
    return video


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

    # Only delete local files inside the managed media directory.
    media_path = video.get('file_path')
    if media_path and os.path.exists(media_path):
        media_dir = Path('data/media').resolve()
        candidate = Path(media_path).resolve()
        if os.path.commonpath([str(media_dir), str(candidate)]) == str(media_dir):
            os.remove(candidate)

    return {"deleted": True, "video_id": video_id, "chunks_removed": chunks_removed}

from fastapi.responses import FileResponse

@router.get("/{video_id}/media")
def get_video_media(video_id: str):
    video = get_video(video_id)
    if not video or not video.get('file_path'):
        raise HTTPException(status_code=404, detail="Media not found")
        
    file_path = video['file_path']
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="File missing")
        
    # Security: Path traversal check
    abs_media_dir = Path("data/media").resolve()
    abs_file_path = Path(file_path).resolve()
    if os.path.commonpath([str(abs_media_dir), str(abs_file_path)]) != str(abs_media_dir):
        raise HTTPException(status_code=403, detail="Forbidden")

    return FileResponse(abs_file_path, headers={"Accept-Ranges": "bytes"})

