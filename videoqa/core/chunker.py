import json
import os
import math
from videoqa.config import config

def merge_chunks(input_dir: str = "jsons", output_dir: str = "newjsons") -> None:
    n = config.get("chunking", {}).get("merge_window_size", 5)
    os.makedirs(output_dir, exist_ok=True)
    for filename in os.listdir(input_dir):
        if filename.endswith(".json"):
            file_path = os.path.join(input_dir, filename)
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                new_chunks = []
                num_chunks = len(data['chunks'])
                num_groups = math.ceil(num_chunks / n)
                for i in range(num_groups):
                    start_idx = i * n
                    end_idx = min((i + 1) * n, num_chunks)
                    chunk_group = data['chunks'][start_idx:end_idx]
                    if not chunk_group:
                        continue
                    new_chunks.append({
                        "number": data['chunks'][0]['number'],
                        "title": chunk_group[0]['title'],
                        "start": chunk_group[0]['start'],
                        "end": chunk_group[-1]['end'],
                        "text": " ".join([chunk['text'] for chunk in chunk_group]),
                        "chunk_index": i
                    })
                with open(os.path.join(output_dir, filename), "w", encoding="utf-8") as out_f:
                    json.dump({"chunks": new_chunks, "text": data.get('text', "")}, out_f, ensure_ascii=False, indent=2)

def process_json_chunks(segments: list[dict], title: str, video_id: str) -> list[dict]:
    """
    Takes a list of segment dicts (as returned by parse_captions or transcribe_audio)
    and chunks them based on config (or fixed 5 segments for now).
    Returns a list of chunk dicts ready for insertion into SQLite/Chroma.
    """
    import uuid
    n = config.get("chunking", {}).get("merge_window_size", 5)
    new_chunks = []
    
    num_chunks = len(segments)
    num_groups = math.ceil(num_chunks / n)
    
    for i in range(num_groups):
        start_idx = i * n
        end_idx = min((i + 1) * n, num_chunks)
        chunk_group = segments[start_idx:end_idx]
        if not chunk_group:
            continue
            
        combined_text = " ".join([seg.get('text_english', '') for seg in chunk_group])
        word_count = len(combined_text.split())
        
        new_chunks.append({
            "chunk_id": str(uuid.uuid4()),
            "video_id": video_id,
            "chunk_index": i,
            "start_seconds": chunk_group[0]['start_seconds'],
            "end_seconds": chunk_group[-1]['end_seconds'],
            "text": combined_text,
            "text_original": " ".join([seg.get('text_original', '') for seg in chunk_group]),
            "word_count": word_count,
            "language": chunk_group[0].get('language', 'en'),
            "title": title
        })
        
    return new_chunks
