import os
import yt_dlp
import logging

logger = logging.getLogger(__name__)

# Basic configuration to enable NodeJS to avoid throttling
YDL_OPTS_BASE = {
    'js_runtimes': {'node': {}},
    'quiet': True,
    'no_warnings': True,
    'noplaylist': True,
    'ignoreerrors': True
}

def fetch_metadata(url: str) -> dict:
    """
    Fetches video metadata using yt-dlp.
    Returns a dictionary of relevant metadata fields.
    """
    opts = {**YDL_OPTS_BASE, 'extract_flat': False}
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=False)
        return {
            'video_id': info.get('id'),
            'title': info.get('title'),
            'channel': info.get('uploader'),
            'duration_seconds': info.get('duration'),
            'thumbnail_url': info.get('thumbnail'),
            'upload_date': info.get('upload_date'),
            'description': info.get('description', '')[:500] if info.get('description') else '',
            'detected_language': info.get('language', 'auto')
        }

def download_captions(url: str, output_dir: str) -> str | None:
    """
    Attempts to download existing captions (VTT/SRT).
    Returns the path to the downloaded caption file, or None if no captions found.
    """
    os.makedirs(output_dir, exist_ok=True)
    
    # We want English or Hindi subs
    opts = {
        **YDL_OPTS_BASE,
        'skip_download': True,
        'writesubtitles': True,
        'writeautomaticsub': True,
        'subtitleslangs': ['en', 'hi'],
        'outtmpl': os.path.join(output_dir, '%(id)s.%(ext)s'),
    }
    
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=True)
            if not info:
                return None
            vid_id = info.get('id')
            
            # Check if any subtitle file was created
            for f in os.listdir(output_dir):
                if f.startswith(vid_id) and (f.endswith('.vtt') or f.endswith('.srt')):
                    return os.path.join(output_dir, f)
    except Exception as e:
        logger.warning(f"Failed to download captions: {e}")
                
    return None

def download_audio(url: str, output_dir: str) -> str:
    """
    Downloads audio-only using yt-dlp.
    Returns the path to the downloaded audio file.
    """
    os.makedirs(output_dir, exist_ok=True)
    opts = {
        **YDL_OPTS_BASE,
        'format': 'bestaudio/best',
        'outtmpl': os.path.join(output_dir, '%(id)s.%(ext)s'),
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '0',
        }],
    }
    
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=True)
        return os.path.join(output_dir, f"{info.get('id')}.mp3")
