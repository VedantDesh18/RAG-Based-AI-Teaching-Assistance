import pytest
from videoqa.utils.url_parser import extract_video_info, parse_youtube_url

def test_youtube_url_parsing():
    valid_id = "dQw4w9WgXcQ"
    
    # 10+ standard YouTube URL formats
    urls = [
        f"https://www.youtube.com/watch?v={valid_id}",
        f"http://www.youtube.com/watch?v={valid_id}",
        f"https://youtube.com/watch?v={valid_id}",
        f"https://m.youtube.com/watch?v={valid_id}",
        f"https://youtu.be/{valid_id}",
        f"http://youtu.be/{valid_id}",
        f"https://www.youtube.com/embed/{valid_id}",
        f"https://youtube.com/embed/{valid_id}",
        f"https://www.youtube.com/shorts/{valid_id}",
        f"https://youtube.com/shorts/{valid_id}",
        f"https://www.youtube.com/v/{valid_id}",
        f"https://www.youtube.com/watch?v={valid_id}&feature=youtu.be&t=10"
    ]
    
    for url in urls:
        assert parse_youtube_url(url) == valid_id
        info = extract_video_info(url)
        assert info['source_type'] == 'youtube'
        assert info['video_id'] == valid_id

def test_direct_url_parsing():
    direct_url = "https://example.com/video.mp4"
    info = extract_video_info(direct_url)
    assert info['source_type'] == 'direct_url'
    assert len(info['video_id']) == 16
    assert info['source_url'] == direct_url

def test_invalid_youtube_url():
    # ID is too short (not 11 chars), so it should fallback to direct_url hashing
    invalid_url = "https://www.youtube.com/watch?v=123"
    info = extract_video_info(invalid_url)
    assert info['source_type'] == 'direct_url'
