import os
import json
import joblib
import argparse
import uuid
import hashlib
from datetime import datetime
from videoqa.db.sqlite import run_migrations, upsert_video, insert_transcript_segments, insert_chunks
from videoqa.vectorstore.chroma import upsert_vectors

def generate_video_id(filename: str) -> str:
    # Deterministic video_id from filename
    return hashlib.md5(filename.encode()).hexdigest()[:11]

def generate_chunk_id(video_id: str, chunk_index: int) -> str:
    namespace = uuid.NAMESPACE_OID
    return str(uuid.uuid5(namespace, f"{video_id}_{chunk_index}"))

def migrate(dry_run: bool = True):
    print(f"Starting migration. Dry run: {dry_run}")
    
    if not dry_run:
        run_migrations()
        print("Migrations ran.")
        
    jsons_dir = "jsons"
    newjsons_dir = "newjsons"
    
    videos_to_upsert = []
    segments_to_insert = []
    
    total_segments = 0
    total_chunks = 0
    
    # Pass 1: Parse raw segments from jsons/
    files = [f for f in os.listdir(jsons_dir) if f.endswith('.json')]
    for file in files:
        video_id = generate_video_id(file)
        with open(os.path.join(jsons_dir, file), 'r', encoding='utf-8') as f:
            data = json.load(f)
            chunks = data.get('chunks', [])
            
            # Reconstruct video metadata from first chunk
            if chunks:
                number = chunks[0].get('number', '')
                title = chunks[0].get('title', file.replace('.json', ''))
                duration = chunks[-1].get('end', 0)
                
                video = {
                    "id": str(uuid.uuid4()),
                    "video_id": video_id,
                    "source_type": "file_upload",
                    "title": title,
                    "duration_seconds": float(duration),
                    "status": "ready",
                    "created_at": datetime.now().isoformat(),
                    "updated_at": datetime.now().isoformat()
                }
                videos_to_upsert.append(video)
            
            for i, chunk in enumerate(chunks):
                segments_to_insert.append({
                    "video_id": video_id,
                    "segment_index": i,
                    "start_seconds": float(chunk['start']),
                    "end_seconds": float(chunk['end']),
                    "text_original": "",
                    "text_english": chunk['text']
                })
                total_segments += 1

    # Pass 2: Parse merged chunks and embeddings
    chunks_to_insert = []
    chroma_ids = []
    chroma_embeddings = []
    chroma_metadatas = []
    
    try:
        df = joblib.load('embeddings_chunks.joblib')
        has_embeddings = True
    except FileNotFoundError:
        print("embeddings_chunks.joblib not found! Run indexer first.")
        has_embeddings = False

    if has_embeddings:
        # the df contains chunks from newjsons/
        # we can iterate over df
        for i, row in df.iterrows():
            filename = f"{row['number']}-{row['title']}.mp3.json" if 'number' in row else "unknown" # Need to derive filename or just use title?
            # Wait, df doesn't have filename directly, but we can match it.
            # Actually, the file names in jsons/ are like "01-how to install nodejs.mp3.json"
            # df has 'number' and 'title'. We can reconstruct it.
            number = str(row['number'])
            title = str(row['title'])
            # Need exact filename to match video_id. We'll search `files`
            matching_file = next((f for f in files if f.startswith(number) and title in f), None)
            if not matching_file:
                # fallback
                matching_file = f"{number}-{title}.mp3.json"
            
            video_id = generate_video_id(matching_file)
            chunk_idx = int(row.get('chunk_index', i)) # if missing, fallback to i
            chunk_id = generate_chunk_id(video_id, chunk_idx)
            
            text = str(row['text'])
            start = float(row['start'])
            end = float(row['end'])
            
            chunks_to_insert.append({
                "chunk_id": chunk_id,
                "video_id": video_id,
                "chunk_index": chunk_idx,
                "start_seconds": start,
                "end_seconds": end,
                "text": text,
                "text_original": "",
                "word_count": len(text.split()),
                "language": "en"
            })
            
            chroma_ids.append(chunk_id)
            chroma_embeddings.append(list(row['embedding']))
            chroma_metadatas.append({
                "video_id": video_id,
                "title": title,
                "start_seconds": start,
                "end_seconds": end,
                "text": text,
                "chunk_index": chunk_idx,
                "language": "en"
            })
            total_chunks += 1

    print(f"Found {len(videos_to_upsert)} videos")
    print(f"Found {total_segments} raw segments")
    print(f"Found {total_chunks} chunks with embeddings")
    
    if not dry_run:
        for v in videos_to_upsert:
            upsert_video(v)
        print("Videos upserted to SQLite.")
        
        insert_transcript_segments(segments_to_insert)
        print("Transcript segments inserted to SQLite.")
        
        insert_chunks(chunks_to_insert)
        print("Chunks inserted to SQLite (FTS will sync via triggers).")
        
        if total_chunks > 0:
            upsert_vectors(chroma_ids, chroma_embeddings, chroma_metadatas)
            print("Vectors upserted to ChromaDB.")
        
        print("Migration complete!")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="Print counts without writing")
    args = parser.parse_args()
    migrate(dry_run=args.dry_run)
