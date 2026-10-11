import json
import sqlite3

with open("eval/golden_questions/starter_set.json", "r") as f:
    questions = json.load(f)

conn = sqlite3.connect("data/db/videoqa.db")
conn.row_factory = sqlite3.Row
cursor = conn.cursor()

out = []
for q in questions:
    if not q["in_domain"]: continue
    
    q_out = f"--- Q{q['id'].split('_')[1]}: {q['question']} ---\n"
    q_out += f"Video: {q['video_id']}\n"
    curr_start = q['answer_spans'][0]['start_seconds'] if q['answer_spans'] else 0
    
    # get context from curr_start - 60 to curr_start + 120
    cursor.execute("SELECT start_seconds, end_seconds, text_english FROM transcript_segments WHERE video_id = ? AND start_seconds >= ? AND start_seconds <= ? ORDER BY start_seconds", (q['video_id'], max(0, curr_start - 60), curr_start + 120))
    segments = cursor.fetchall()
    
    for s in segments:
        q_out += f"[{s['start_seconds']:.2f}-{s['end_seconds']:.2f}] {s['text_english']}\n"
    q_out += "\n"
    out.append(q_out)
    
with open("scratch_media/question_contexts.txt", "w", encoding="utf-8") as f:
    f.write("\n".join(out))
