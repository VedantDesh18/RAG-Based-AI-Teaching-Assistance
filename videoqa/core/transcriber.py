import os
import re
import json
import webvtt
import tempfile
from typing import List, Dict, Any

def parse_time_str(time_str: str) -> float:
    # 00:00:00.000
    parts = time_str.replace(',', '.').split(':')
    if len(parts) == 3:
        h, m, s = parts
        return int(h) * 3600 + int(m) * 60 + float(s)
    elif len(parts) == 2:
        m, s = parts
        return int(m) * 60 + float(s)
    return float(parts[0])

def parse_captions(file_path: str, video_id: str) -> List[Dict[str, Any]]:
    """
    Parses VTT or SRT files into segment dictionaries.
    """
    segments = []
    
    # If it's an SRT, we can try to convert or just parse it manually
    # webvtt-py supports parsing VTT easily. If it's SRT, webvtt-py might fail,
    # so we'll just do a very basic regex fallback if needed.
    
    try:
        if file_path.endswith('.vtt'):
            vtt = webvtt.read(file_path)
            for i, caption in enumerate(vtt):
                segments.append({
                    'segment_index': i,
                    'start_seconds': parse_time_str(caption.start),
                    'end_seconds': parse_time_str(caption.end),
                    'text_english': caption.text.replace('\n', ' ').strip(),
                    'text_original': caption.text.replace('\n', ' ').strip(),
                    'language': 'en' # Assuming English for now, yt-dlp requested en/hi
                })
            return segments
    except Exception as e:
        print(f"Failed to parse VTT with webvtt: {e}")
        pass

    # Basic Regex Parser for SRT/VTT
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
        
    pattern = re.compile(r'(\d{2}:\d{2}:\d{2}[,.]\d{3})\s*-->\s*(\d{2}:\d{2}:\d{2}[,.]\d{3})\s*?\n(.*?)(?=\n\n|\Z)', re.DOTALL)
    matches = pattern.findall(content)
    
    for i, match in enumerate(matches):
        start_str, end_str, text = match
        # Clean text
        text = re.sub(r'<[^>]+>', '', text) # remove html tags
        text = text.replace('\n', ' ').strip()
        
        segments.append({
            'segment_index': i,
            'start_seconds': parse_time_str(start_str),
            'end_seconds': parse_time_str(end_str),
            'text_english': text,
            'text_original': text,
            'language': 'en'
        })
        
    return segments

def transcribe_audio(audio_path: str, video_id: str, offset: float = 0.0, use_faster_whisper: bool = True) -> dict:
    """
    Transcribes audio. If offset > 0, shifts timestamps.
    Returns a dict with 'segments' and 'language'.
    """
    if use_faster_whisper:
        from faster_whisper import WhisperModel
        whisper_model_name = os.getenv("WHISPER_MODEL", "large-v2")
        whisper_device = os.getenv("WHISPER_DEVICE", "cpu")
        whisper_compute = os.getenv("WHISPER_COMPUTE_TYPE", "int8")
        model = WhisperModel(whisper_model_name, device=whisper_device, compute_type=whisper_compute)
        
        # Auto-detect language if needed, but faster-whisper does this automatically 
        # for the first 30s. We'll just run it.
        segments_gen, info = model.transcribe(audio_path, beam_size=5)
        detected_lang = info.language
        
        segments = []
        for i, seg in enumerate(segments_gen):
            segments.append({
                'segment_index': i,
                'start_seconds': seg.start + offset,
                'end_seconds': seg.end + offset,
                'text_original': seg.text.strip(),
                'text_english': seg.text.strip(), # We'll do a translation pass if needed, but skip for now
                'language': detected_lang
            })
            
        return {
            'segments': segments,
            'language': detected_lang
        }
    else:
        import whisper
        model = whisper.load_model("large-v2")
        result = model.transcribe(audio_path)
        detected_lang = result.get('language', 'en')
        
        segments = []
        for i, seg in enumerate(result.get('segments', [])):
            segments.append({
                'segment_index': i,
                'start_seconds': seg['start'] + offset,
                'end_seconds': seg['end'] + offset,
                'text_original': seg['text'].strip(),
                'text_english': seg['text'].strip(),
                'language': detected_lang
            })
            
        return {
            'segments': segments,
            'language': detected_lang
        }
