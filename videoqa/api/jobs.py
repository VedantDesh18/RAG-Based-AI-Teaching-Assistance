from datetime import datetime, timezone
from fastapi import APIRouter, BackgroundTasks, HTTPException
from videoqa.db.sqlite import get_video, update_video_status
from videoqa.core.ingestion import ingest_url, ingest_file, reset_for_retry
from videoqa.storage import resolve_media_path

router = APIRouter(prefix="/api/jobs", tags=["jobs"])

ACTIVE_STATUSES = {"queued", "downloading", "transcribing", "chunking", "embedding"}
STAGES = ["queued", "downloading", "transcribing", "chunking", "embedding", "ready"]

@router.get("/{video_id}")
def get_job_status(video_id: str):
    video = get_video(video_id)
    if not video:
        raise HTTPException(status_code=404, detail="Video not found")
        
    return {
        "job_id": video['video_id'],
        "video_id": video['video_id'],
        "status": video['status'],
        "stage": video['status'],
        "stage_index": STAGES.index(video['status']) if video['status'] in STAGES else None,
        "stages": STAGES,
        "error_message": video.get('error_message'),
        "retry_count": video.get('retry_count', 0),
        "created_at": video.get('created_at'),
        "updated_at": video.get('updated_at'),
    }


@router.post("/{video_id}/cancel")
def cancel_job(video_id: str):
    video = get_video(video_id)
    if not video:
        raise HTTPException(status_code=404, detail="Video job not found")
    if video.get('status') not in ACTIVE_STATUSES:
        raise HTTPException(status_code=409, detail="Only active jobs can be cancelled")
    changed = update_video_status(video_id, 'cancelled', datetime.now(timezone.utc).isoformat(), allowed_current_statuses=ACTIVE_STATUSES)
    if not changed:
        raise HTTPException(status_code=409, detail="Only active jobs can be cancelled")
    return {"job_id": video_id, "video_id": video_id, "status": "cancelled"}


@router.post("/{video_id}/retry")
def retry_job(video_id: str, background_tasks: BackgroundTasks):
    video = get_video(video_id)
    if not video:
        raise HTTPException(status_code=404, detail="Video job not found")
    if int(video.get('retry_count') or 0) >= 3:
        raise HTTPException(status_code=409, detail="This job has reached its retry limit")
    if video.get('source_type') != 'file_upload' and not video.get('source_url'):
        raise HTTPException(status_code=409, detail="The original source is no longer available for retry")
    try:
        video = reset_for_retry(video_id)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if video.get('source_type') == 'file_upload':
        source_path = resolve_media_path(video.get('file_path')) if video.get('file_path') else None
        if not source_path:
            update_video_status(video_id, 'failed', datetime.now(timezone.utc).isoformat(), "The original uploaded media file is missing.")
            raise HTTPException(status_code=409, detail="The original uploaded media file is no longer available for retry")
        background_tasks.add_task(ingest_file, str(source_path), video_id, video['title'])
    else:
        background_tasks.add_task(ingest_url, video['source_url'], video_id)
    return {"job_id": video_id, "video_id": video_id, "status": "queued", "retry_count": video.get('retry_count', 0)}
