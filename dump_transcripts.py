import sqlite3
import os

db_path = "data/db/videoqa.db"
if not os.path.exists(db_path):
    print(f"DB not found at {db_path}")
    exit(1)

conn = sqlite3.connect(db_path)
conn.row_factory = sqlite3.Row
cursor = conn.cursor()

# Get all videos
cursor.execute("SELECT video_id, title FROM videos")
videos = cursor.fetchall()

os.makedirs("scratch_media/transcripts", exist_ok=True)

for video in videos:
    v_id = video['video_id']
    title = video['title']
    
    cursor.execute("SELECT start_seconds, end_seconds, text_original FROM transcript_segments WHERE video_id = ? ORDER BY start_seconds", (v_id,))
    segments = cursor.fetchall()
    
    with open(f"scratch_media/transcripts/{v_id}.txt", "w", encoding="utf-8") as f:
        f.write(f"Title: {title}\n")
        f.write(f"Video ID: {v_id}\n\n")
        for seg in segments:
            f.write(f"[{seg['start_seconds']:.2f} - {seg['end_seconds']:.2f}] {seg['text_original']}\n")

print("Dumped all transcripts to scratch_media/transcripts/")

# Also search for OOD terms in chunks to get hit counts
ood_terms = ['react', 'hook', 'python', 'decorator', 'docker', 'sql', 'join']
print("\nOOD Term Hits:")
for term in ood_terms:
    cursor.execute("SELECT count(*) as c FROM transcript_segments WHERE text_original LIKE ?", (f"%{term}%",))
    count = cursor.fetchone()['c']
    print(f"'{term}': {count} hits")
