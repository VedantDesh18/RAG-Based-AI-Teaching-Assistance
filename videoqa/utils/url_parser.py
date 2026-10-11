import re
import hashlib
from urllib.parse import urlparse, parse_qs

def parse_youtube_url(url: str) -> str | None:
    """
    Extracts the 11-character YouTube video ID from various standard YouTube URL formats.
    Returns None if no valid ID is found.
    """
    # Patterns for different formats:
    # 1. youtu.be/ID
    # 2. youtube.com/watch?v=ID
    # 3. youtube.com/embed/ID
    # 4. youtube.com/shorts/ID
    # 5. youtube.com/v/ID
    
    parsed = urlparse(url)
    
    if parsed.hostname in ('youtu.be', 'www.youtu.be'):
        return parsed.path[1:] if parsed.path else None
        
    if parsed.hostname in ('youtube.com', 'www.youtube.com', 'm.youtube.com'):
        if parsed.path == '/watch':
            qs = parse_qs(parsed.query)
            return qs.get('v', [None])[0]
            
        for prefix in ('/embed/', '/shorts/', '/v/'):
            if parsed.path.startswith(prefix):
                return parsed.path[len(prefix):]
                
    return None

def extract_video_info(url: str) -> dict:
    """
    Categorizes the URL and extracts its unique ID.
    Returns a dict with 'source_type' ('youtube' or 'direct_url') and 'video_id'.
    """
    yt_id = parse_youtube_url(url)
    
    if yt_id and len(yt_id) == 11:
        return {
            'source_type': 'youtube',
            'video_id': yt_id,
            'source_url': url
        }
        
    # If not YouTube, treat as direct URL and hash the URL for a unique ID
    # In a full implementation, we might want to do a quick HEAD request to verify MIME type.
    hashed_id = hashlib.sha256(url.encode('utf-8')).hexdigest()[:16]
    return {
        'source_type': 'direct_url',
        'video_id': hashed_id,
        'source_url': url
    }
