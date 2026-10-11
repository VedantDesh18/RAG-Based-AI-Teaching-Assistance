from fastapi import APIRouter, BackgroundTasks, HTTPException, UploadFile, File, Response, status
from pydantic import BaseModel
from videoqa.core.ingestion import ingest_url, ingest_file, make_queued_url_video, make_queued_file_video
from videoqa.config import config
import os
import uuid
from pathlib import Path
from urllib.parse import urlparse

router = APIRouter(prefix="/api/ingest", tags=["ingest"])

class IngestUrlRequest(BaseModel):
    url: str


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
async def ingest_file_endpoint(background_tasks: BackgroundTasks, file: UploadFile = File(...)):
    if not file.filename:
        raise HTTPException(status_code=422, detail="Choose a video or audio file to upload.")

    original_filename = Path(file.filename).name
    extension = Path(original_filename).suffix.lower()
    ingestion_config = config.get('ingestion', {})
    allowed_extensions = set(ingestion_config.get('supported_extensions', []))
    max_upload_bytes = int(ingestion_config.get('max_upload_bytes', 2 * 1024 * 1024 * 1024))
    if extension not in allowed_extensions:
        supported = ', '.join(sorted(allowed_extensions))
        raise HTTPException(status_code=422, detail=f"Unsupported file type. Supported formats: {supported}.")

    os.makedirs("data/media", exist_ok=True)
    video_id = str(uuid.uuid4())[:16]
    file_path = f"data/media/{video_id}{extension}"
    received_bytes = 0

    try:
        with open(file_path, "wb") as destination:
            while chunk := await file.read(1024 * 1024):
                received_bytes += len(chunk)
                if received_bytes > max_upload_bytes:
                    destination.close()
                    os.remove(file_path)
                    raise HTTPException(status_code=413, detail="This file exceeds the 2 GB upload limit.")
                destination.write(chunk)
    except HTTPException:
        raise
    except Exception as exc:
        if os.path.exists(file_path):
            os.remove(file_path)
        raise HTTPException(status_code=500, detail="Unable to save the uploaded file.") from exc
    finally:
        await file.close()

    video = make_queued_file_video(file_path, video_id, original_filename)
    background_tasks.add_task(ingest_file, file_path, video_id, original_filename)
    return job_response(video, "queued", "Upload complete. Processing has started.")
