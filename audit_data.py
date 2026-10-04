import sqlite3
import joblib
import os
import chromadb

# SQLite
try:
    db = sqlite3.connect('data/db/videoqa.db')
    c = db.cursor()
    def q(query):
        try: return c.execute(query).fetchone()[0]
        except Exception as e: return str(e)

    videos = q('SELECT COUNT(*) FROM videos')
    segments = q('SELECT COUNT(*) FROM transcript_segments')
    chunks = q('SELECT COUNT(*) FROM chunks')
    fts = q('SELECT COUNT(*) FROM chunks_fts')

    print(f'SQLite - videos: {videos}')
    print(f'SQLite - transcript_segments: {segments}')
    print(f'SQLite - chunks: {chunks}')
    print(f'SQLite - chunks_fts: {fts}')
except Exception as e:
    print(f'SQLite error: {e}')

# Chroma
try:
    client = chromadb.PersistentClient(path='data/chroma')
    collection = client.get_collection('video_chunks')
    print(f'Chroma collection count: {collection.count()}')
except Exception as e:
    print(f'Chroma error: {e}')

# Joblib
try:
    emb1 = joblib.load('embeddings.joblib')
    print(f'embeddings.joblib rows: {len(emb1)}')
except Exception as e: print(f'embeddings.joblib error: {e}')

try:
    emb2 = joblib.load('embeddings_chunks.joblib')
    print(f'embeddings_chunks.joblib rows: {len(emb2)}')
except Exception as e: print(f'embeddings_chunks.joblib error: {e}')

# Directories
def count_dir(path):
    if not os.path.exists(path): return 0
    return len([f for f in os.listdir(path) if f.endswith('.json')])

print(f'jsons/ files: {count_dir("jsons")}')
print(f'newjsons/ files: {count_dir("newjsons")}')
