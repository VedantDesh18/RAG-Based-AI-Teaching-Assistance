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
