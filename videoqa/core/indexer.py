import requests
import os
import json
import pandas as pd
import joblib
from videoqa.config import config

def create_embedding(text_list):
    r = requests.post(f"{config['ollama_url']}/api/embed", json={
        "model": config['model_names']['embedding'],
        "input": text_list
    })
    embedding = r.json()["embeddings"]
    return embedding

def index_chunks(input_dir: str = "newjsons", output_file: str = None) -> None:
    if output_file is None:
        output_file = config['paths']['index']
    
    jsons_files = [f for f in os.listdir(input_dir) if f.endswith('.json')]
    my_dicts = []
    chunk_id = 0
    for json_file in jsons_files:
        with open(os.path.join(input_dir, json_file), encoding="utf-8") as f:
            content = json.load(f)
        texts = [c['text'] for c in content['chunks']]
        if not texts:
            continue
        
        # Batching Ollama calls (e.g. batch size 64)
        embeddings = []
        batch_size = 64
        for i in range(0, len(texts), batch_size):
            batch_texts = texts[i:i+batch_size]
            batch_embeds = create_embedding(batch_texts)
            embeddings.extend(batch_embeds)
            
        for i, chunk in enumerate(content['chunks']):
            chunk['chunk_id'] = chunk_id
            chunk['embedding'] = embeddings[i]
            # Ensure chunk_index is present
            if 'chunk_index' not in chunk:
                chunk['chunk_index'] = i
            chunk_id += 1
            my_dicts.append(chunk)
            
    df = pd.DataFrame.from_records(my_dicts)
    joblib.dump(df, output_file)
