import requests
import os
import json
import pandas as pd
import joblib
import videoqa.config as config_module

def create_embedding(text_list):
    r = requests.post(f"{config_module.config['ollama_url']}/api/embed", json={
        "model": config_module.config['model_names']['embedding'],
        "input": text_list
    })
    embedding = r.json()["embeddings"]
    return embedding

from videoqa.vectorstore.chroma import upsert_vectors
from videoqa.db.sqlite import insert_chunks, set_chunk_count

def index_chunks(chunks: list[dict]) -> None:
    if not chunks:
        return
        
    texts = [c['text'] for c in chunks]
    
    # Batching Ollama calls
    embeddings = []
    batch_size = 64
    for i in range(0, len(texts), batch_size):
        batch_texts = texts[i:i+batch_size]
        batch_embeds = create_embedding(batch_texts)
        embeddings.extend(batch_embeds)
        
    # Prepare metadata for Chroma and insert into SQLite
    ids = []
    metadatas = []
    
    for i, chunk in enumerate(chunks):
        chunk['embedding'] = embeddings[i]
        
        # Meta for Chroma (must be simple types)
        meta = {
            'video_id': chunk['video_id'],
            'chunk_index': chunk['chunk_index'],
            'start_seconds': chunk['start_seconds'],
            'end_seconds': chunk['end_seconds'],
            'text': chunk['text'],
            'title': chunk.get('title', '')
        }
        
        ids.append(chunk['chunk_id'])
        metadatas.append(meta)
        
    # Upsert to Chroma
    upsert_vectors(ids, embeddings, metadatas)
    
    # Insert to SQLite
    insert_chunks(chunks)
    set_chunk_count(chunks[0]['video_id'], len(chunks))
