"""CLI utility to safely reprocess/retranscribe an existing video without deleting the source file.

Usage:
    python scripts/reprocess_video.py <video_id> [language]

Examples:
    python scripts/reprocess_video.py a6e694ff-15d6-52ba-83af-764de603be6a hi
    python scripts/reprocess_video.py qw8G2MAdu-k en
"""

import sys
import logging
from videoqa.db.sqlite import get_video
from videoqa.core.ingestion import ingest_file, ingest_url, reset_for_reprocess
from videoqa.storage import resolve_media_path

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("reprocess_video")


def reprocess(video_id: str, language: str | None = None):
    video = get_video(video_id)
    if not video:
        logger.error("Video '%s' not found in database.", video_id)
        sys.exit(1)

    logger.info("Resetting derived artifacts for video: %s ('%s')", video_id, video.get("title"))
    try:
        video = reset_for_reprocess(video_id)
    except Exception as exc:
        logger.error("Failed to reset video for reprocess: %s", exc)
        sys.exit(1)

    logger.info("Starting ingestion with language=%s", language or "auto")
    if video.get("source_type") == "file_upload":
        source_path = resolve_media_path(video.get("file_path"))
        if not source_path:
            logger.error("Media file for video '%s' could not be resolved.", video_id)
            sys.exit(1)
        result = ingest_file(str(source_path), video_id, video.get("title", ""), language=language)
    else:
        result = ingest_url(video.get("source_url", ""), video_id, language=language)

    logger.info("Reprocessing completed with result: %s", result)
    return result


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    target_video_id = sys.argv[1].strip()
    target_lang = sys.argv[2].strip() if len(sys.argv) > 2 else None
    reprocess(target_video_id, target_lang)

