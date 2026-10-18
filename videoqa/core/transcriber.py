import os
import re
import json
import logging
import webvtt
import tempfile
from typing import List, Dict, Any

# Ensure Hugging Face Hub uses standard reliable download instead of buggy Xet/CAS client
os.environ["HF_HUB_DISABLE_XET"] = "1"
os.environ["HF_HUB_DISABLE_SYMLINKS_WARNING"] = "1"

# Compatibility patch for PyAV 19 where metadata_errors kwarg was removed
try:
    import av
    _orig_av_open = av.open
    def _compat_av_open(*args, **kwargs):
        kwargs.pop("metadata_errors", None)
        return _orig_av_open(*args, **kwargs)
    av.open = _compat_av_open
except Exception:
    pass

logger = logging.getLogger(__name__)

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

_cached_whisper_model = None
_cached_whisper_key = None

def _get_whisper_model(model_name: str, device: str, compute_type: str):
    global _cached_whisper_model, _cached_whisper_key
    key = (model_name, device, compute_type)
    if _cached_whisper_model is not None and _cached_whisper_key == key:
        return _cached_whisper_model

    from faster_whisper import WhisperModel
    try:
        model = WhisperModel(model_name, device=device, compute_type=compute_type)
        _cached_whisper_model = model
        _cached_whisper_key = key
        return model
    except Exception as exc:
        if model_name != "small":
            logger.warning(
                "Failed to initialize Whisper model '%s' (%s). Falling back to locally cached 'small' model.",
                model_name,
                exc,
            )
            fallback_model = WhisperModel("small", device=device, compute_type=compute_type)
            _cached_whisper_model = fallback_model
            _cached_whisper_key = ("small", device, compute_type)
            return fallback_model
        raise

def transcribe_audio(audio_path: str, video_id: str, offset: float = 0.0, use_faster_whisper: bool = True) -> dict:
    """
    Transcribes audio. If offset > 0, shifts timestamps.
    Returns a dict with 'segments' and 'language'.
    """
    if use_faster_whisper:
        whisper_model_name = os.getenv("WHISPER_MODEL", "small")
        whisper_device = os.getenv("WHISPER_DEVICE", "cpu")
        whisper_compute = os.getenv("WHISPER_COMPUTE_TYPE", "int8")
        model = _get_whisper_model(whisper_model_name, device=whisper_device, compute_type=whisper_compute)
        
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
