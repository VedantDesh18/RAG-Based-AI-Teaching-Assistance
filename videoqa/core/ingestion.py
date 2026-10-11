import os
import uuid
from datetime import datetime, timezone
import logging

from videoqa.utils.url_parser import extract_video_info
from videoqa.core.downloader import fetch_metadata, download_captions, download_audio
from videoqa.core.transcriber import parse_captions, transcribe_audio
from videoqa.core.audio import split_audio
from videoqa.core.chunker import process_json_chunks
from videoqa.core.indexer import index_chunks
from videoqa.db.sqlite import (
    upsert_video,
    get_video,
    insert_transcript_segments,
    reset_video_content,
)
from videoqa.vectorstore.chroma import delete_video_chroma

logger = logging.getLogger(__name__)

ACTIVE_STATUSES = {"queued", "downloading", "transcribing", "chunking", "embedding"}


class JobCancelled(Exception):
    """Internal control flow signal for a job cancelled from the API."""


def make_queued_url_video(url: str) -> tuple[dict, bool]:
    """Create (or reuse) the durable job record before the background task starts."""
    info = extract_video_info(url)
    video_id = info['video_id']
    existing = get_video(video_id)
    if existing and existing.get('status') == 'ready':
        return existing, True

    now = datetime.now(timezone.utc).isoformat()
    if existing:
        video = existing
        video.update({
            'source_type': info['source_type'],
            'source_url': url,
            'status': existing.get('status') if existing.get('status') in ACTIVE_STATUSES else 'queued',
            'error_message': None,
            'updated_at': now,
        })
    else:
        video = {
            'id': str(uuid.uuid4()),
            'video_id': video_id,
            'source_type': info['source_type'],
            'source_url': url,
            'title': 'Preparing video metadata…',
            'status': 'queued',
            'created_at': now,
            'updated_at': now,
        }
    upsert_video(video)
    return video, False


def make_queued_file_video(file_path: str, video_id: str, original_filename: str) -> dict:
    now = datetime.now(timezone.utc).isoformat()
    video = {
        'id': str(uuid.uuid4()),
        'video_id': video_id,
        'source_type': 'file_upload',
        'source_url': None,
        'title': original_filename,
        'file_path': file_path,
        'status': 'queued',
        'error_message': None,
        'created_at': now,
        'updated_at': now,
    }
    upsert_video(video)
    return video


def ensure_job_active(video_id: str) -> None:
    current = get_video(video_id)
    if current and current.get('status') == 'cancelled':
        raise JobCancelled()

def update_status(video: dict, status: str, error_message: str | None = None):
    ensure_job_active(video['video_id'])
    video['status'] = status
    video['updated_at'] = datetime.now(timezone.utc).isoformat()
    video['error_message'] = error_message
    upsert_video(video)
    logger.info(f"Video {video['video_id']} status -> {status}")

def ingest_url(url: str, video_id: str | None = None):
    """
    Orchestrates the ingestion pipeline for a URL.
    """
    info = extract_video_info(url)
    resolved_video_id = video_id or info['video_id']
    video = get_video(resolved_video_id)
    if not video:
        video, already_indexed = make_queued_url_video(url)
        if already_indexed:
            return {"status": "already_indexed", "video_id": video['video_id']}
    elif video.get('status') == 'ready':
        return {"status": "already_indexed", "video_id": resolved_video_id}
        
    try:
        ensure_job_active(resolved_video_id)
        update_status(video, 'downloading')
        
        # 1. Fetch Metadata
        metadata = fetch_metadata(url)
        if metadata:
            # Keep the durable job/video id created from the submitted URL. Some direct
            # hosts expose a different extractor id, which must not orphan the job.
            video.update({key: value for key, value in metadata.items() if key != 'video_id'})
            upsert_video(video)
            
            # Duration limit: 4 hours
            if video.get('duration_seconds', 0) > 4 * 3600:
                raise ValueError("Video duration exceeds 4-hour limit.")
        
        media_dir = "data/media"
        
        # 2. Transcribe
        update_status(video, 'transcribing')
        segments = []
        caption_path = download_captions(url, media_dir)
        
        if caption_path:
            logger.info("Parsing downloaded captions.")
            segments = parse_captions(caption_path, resolved_video_id)
        
        if not segments:
            ensure_job_active(resolved_video_id)
            logger.info("Downloading audio for transcription.")
            audio_path = download_audio(url, media_dir)
            
            parts = split_audio(audio_path, media_dir, max_duration_sec=1800)
            
            all_segments = []
            for part in parts:
                ensure_job_active(resolved_video_id)
                res = transcribe_audio(part['path'], resolved_video_id, offset=part['offset'], use_faster_whisper=True)
                all_segments.extend(res['segments'])
                
            segments = all_segments
            
            # Cleanup media files
            for part in parts:
                if os.path.exists(part['path']):
                    os.remove(part['path'])
            if os.path.exists(audio_path):
                os.remove(audio_path)
                
        if not segments:
            raise ValueError("No transcript segments could be generated.")
            
        # Re-index segments to be continuous
        for i, seg in enumerate(segments):
            seg['segment_index'] = i
            seg['video_id'] = resolved_video_id
            
        insert_transcript_segments(segments)
        
        # 3. Chunking
        update_status(video, 'chunking')
        chunks = process_json_chunks(segments, video['title'], resolved_video_id)
        
        # 4. Embedding
        update_status(video, 'embedding')
        ensure_job_active(resolved_video_id)
        index_chunks(chunks)
        
        # Done
        update_status(video, 'ready')
        return {"status": "success", "video_id": resolved_video_id}
        
    except JobCancelled:
        logger.info("Ingestion cancelled for %s", resolved_video_id)
        return {"status": "cancelled", "video_id": resolved_video_id}
    except Exception as e:
        logger.exception("Ingestion failed for %s", resolved_video_id)
        try:
            update_status(video, 'failed', str(e))
        except JobCancelled:
            return {"status": "cancelled", "video_id": resolved_video_id}
        return {"status": "failed", "video_id": resolved_video_id, "error": str(e)}

def ingest_file(file_path: str, video_id: str, original_filename: str):
    video = get_video(video_id) or make_queued_file_video(file_path, video_id, original_filename)
    
    try:
        ensure_job_active(video_id)
        from videoqa.core.audio import get_audio_duration
        duration = get_audio_duration(file_path)
        video['duration_seconds'] = duration
        upsert_video(video)
        
        update_status(video, 'transcribing')
        
        media_dir = "data/media"
        parts = split_audio(file_path, media_dir, max_duration_sec=1800)
        
        all_segments = []
        for part in parts:
            ensure_job_active(video_id)
            res = transcribe_audio(part['path'], video_id, offset=part['offset'], use_faster_whisper=True)
            all_segments.extend(res['segments'])
            
        segments = all_segments
        
        # Cleanup split parts (keep original file for playback)
        for part in parts:
            if part['path'] != file_path and os.path.exists(part['path']):
                os.remove(part['path'])
                
        if not segments:
            raise ValueError("No transcript segments could be generated.")
            
        for i, seg in enumerate(segments):
            seg['segment_index'] = i
            seg['video_id'] = video_id
            
        insert_transcript_segments(segments)
        
        update_status(video, 'chunking')
        chunks = process_json_chunks(segments, video['title'], video_id)
        
        update_status(video, 'embedding')
        ensure_job_active(video_id)
        index_chunks(chunks)
        
        update_status(video, 'ready')
        return {"status": "success", "video_id": video_id}
        
    except JobCancelled:
        logger.info("Ingestion cancelled for %s", video_id)
        return {"status": "cancelled", "video_id": video_id}
    except Exception as e:
        logger.exception("Ingestion failed for %s", video_id)
        try:
            update_status(video, 'failed', str(e))
        except JobCancelled:
            return {"status": "cancelled", "video_id": video_id}
        return {"status": "failed", "video_id": video_id, "error": str(e)}


def reset_for_retry(video_id: str) -> dict:
    """Clear derived artifacts while retaining the user-owned source and metadata."""
    video = get_video(video_id)
    if not video:
        raise ValueError("Video not found")
    if video.get('status') not in {'failed', 'cancelled'}:
        raise ValueError("Only failed or cancelled jobs can be retried")
    delete_video_chroma(video_id)
    reset_video_content(video_id)
    video['status'] = 'queued'
    video['error_message'] = None
    video['updated_at'] = datetime.now(timezone.utc).isoformat()
    upsert_video(video)
    return video

