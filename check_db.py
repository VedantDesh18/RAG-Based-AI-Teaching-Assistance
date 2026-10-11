import sqlite3
import os

db_path = "data/db/videoqa.db"
if not os.path.exists(db_path):
    print(f"DB not found at {db_path}")
    exit(1)

conn = sqlite3.connect(db_path)
print("Tables:")
print([r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table';").fetchall()])

for table in ['videos', 'transcript_segments', 'chunks']:
    try:
        cols = [r[1] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()]
        print(f"Columns for {table}: {cols}")
    except Exception as e:
        print(e)
