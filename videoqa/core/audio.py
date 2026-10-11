import os
import subprocess
import math
import json

def get_audio_duration(file_path: str) -> float:
    cmd = [
        "ffprobe", "-v", "error", "-show_entries",
        "format=duration", "-of",
        "default=noprint_wrappers=1:nokey=1", file_path
    ]
    result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if result.returncode != 0 or not result.stdout.strip():
        return 0.0
    return float(result.stdout.strip())

def extract_audio(input_path: str, output_path: str) -> None:
    """
    Extracts audio from a video file and saves it as an MP3.
    """
    subprocess.run(["ffmpeg", "-y", "-i", input_path, "-q:a", "0", "-map", "a", output_path], check=True)

def split_audio(input_path: str, output_dir: str, max_duration_sec: int = 1800) -> list[dict]:
    """
    Splits audio into segments of max_duration_sec.
    Returns a list of dicts: [{'path': segment_path, 'offset': start_seconds}]
    """
    duration = get_audio_duration(input_path)
    if duration <= max_duration_sec:
        return [{'path': input_path, 'offset': 0.0}]
        
    os.makedirs(output_dir, exist_ok=True)
    base_name = os.path.splitext(os.path.basename(input_path))[0]
    ext = os.path.splitext(input_path)[1]
    
    segments = []
    num_segments = math.ceil(duration / max_duration_sec)
    
    for i in range(num_segments):
        start_time = i * max_duration_sec
        segment_path = os.path.join(output_dir, f"{base_name}_part{i:03d}{ext}")
        
        # Split using ffmpeg
        cmd = [
            "ffmpeg", "-y", "-i", input_path, 
            "-ss", str(start_time), 
            "-t", str(max_duration_sec), 
            "-c", "copy", segment_path
        ]
        subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        
        segments.append({
            'path': segment_path,
            'offset': float(start_time)
        })
        
    return segments
