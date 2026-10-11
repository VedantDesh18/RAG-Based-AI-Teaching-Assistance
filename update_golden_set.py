import json
import sqlite3
import os

with open("eval/golden_questions/starter_set.json", "r") as f:
    questions = json.load(f)

# Connect to DB to get extra spans
conn = sqlite3.connect("data/db/videoqa.db")
conn.row_factory = sqlite3.Row
cursor = conn.cursor()

def find_extra_spans(keyword):
    cursor.execute("SELECT video_id, start_seconds, end_seconds, text_english FROM transcript_segments WHERE text_english LIKE ?", (f"%{keyword}%",))
    rows = cursor.fetchall()
    spans = []
    for r in rows:
        spans.append({
            "video_id": r['video_id'],
            "start_seconds": round(r['start_seconds'], 2),
            "end_seconds": round(r['end_seconds'], 2)
        })
    # Group adjacent spans
    grouped = []
    if not spans: return grouped
    spans.sort(key=lambda x: (x['video_id'], x['start_seconds']))
    curr = spans[0]
    for i in range(1, len(spans)):
        s = spans[i]
        if s['video_id'] == curr['video_id'] and s['start_seconds'] - curr['end_seconds'] <= 15:
            curr['end_seconds'] = s['end_seconds']
        else:
            grouped.append(curr)
            curr = s
    grouped.append(curr)
    return grouped

primary_spans = {
    "q_1": {"video_id": "f7cc259539c", "start_seconds": 26.0, "end_seconds": 74.0},
    "q_2": {"video_id": "f7cc259539c", "start_seconds": 223.0, "end_seconds": 271.0},
    "q_3": {"video_id": "9a7545f5bbd", "start_seconds": 37.0, "end_seconds": 101.0},
    "q_4": {"video_id": "9a7545f5bbd", "start_seconds": 334.0, "end_seconds": 379.0},
    "q_5": {"video_id": "a19151b49f2", "start_seconds": 17.0, "end_seconds": 139.0},
    "q_6": {"video_id": "a19151b49f2", "start_seconds": 483.0, "end_seconds": 554.0},
    "q_7": {"video_id": "645fa5c93f2", "start_seconds": 13.0, "end_seconds": 67.0},
    "q_8": {"video_id": "645fa5c93f2", "start_seconds": 312.0, "end_seconds": 331.0},
    "q_9": {"video_id": "77a4dcb2e30", "start_seconds": 443.0, "end_seconds": 501.0},
    "q_10": {"video_id": "77a4dcb2e30", "start_seconds": 783.0, "end_seconds": 793.0}, # fallback to original chunk
    "q_11": {"video_id": "241a8ef7fa5", "start_seconds": 4.0, "end_seconds": 127.0},
    "q_12": {"video_id": "241a8ef7fa5", "start_seconds": 629.0, "end_seconds": 805.0},
    "q_13": {"video_id": "91f77563a0a", "start_seconds": 15.5, "end_seconds": 89.0},
    "q_14": {"video_id": "91f77563a0a", "start_seconds": 579.0, "end_seconds": 713.0},
    "q_15": {"video_id": "70dd9371bb7", "start_seconds": 4.0, "end_seconds": 118.0},
    "q_16": {"video_id": "70dd9371bb7", "start_seconds": 474.0, "end_seconds": 566.0},
    "q_17": {"video_id": "7e654e91748", "start_seconds": 5.0, "end_seconds": 132.0},
    "q_18": {"video_id": "7e654e91748", "start_seconds": 522.0, "end_seconds": 596.0},
    "q_19": {"video_id": "3d763901fe2", "start_seconds": 9.0, "end_seconds": 93.0},
    "q_20": {"video_id": "3d763901fe2", "start_seconds": 585.0, "end_seconds": 649.0},
    "q_21": {"video_id": "02106c4bde3", "start_seconds": 8.0, "end_seconds": 37.0},
    "q_22": {"video_id": "40a80d83cb1", "start_seconds": 12.0, "end_seconds": 45.0},
    "q_23": {"video_id": "7d8e4429f5e", "start_seconds": 338.0, "end_seconds": 399.0},
    "q_24": {"video_id": "24350b15787", "start_seconds": 56.0, "end_seconds": 139.0},
    "q_25": {"video_id": "1fef318c007", "start_seconds": 6.0, "end_seconds": 50.0}
}

paraphrased = {
    "q_15": "How can I execute different blocks of code based on whether a specific condition is met or not?",
    "q_17": "What are the standard ways to repeatedly execute a block of code?",
    "q_19": "What is the benefit of using a list-like data structure to hold a collection of items rather than individual variables?",
    "q_21": "What is the best way to group a set of instructions so they can be executed multiple times without rewriting them?",
    "q_22": "What is the advantage of associating data with descriptive string labels rather than relying on sequential numbers?"
}

keyword_mapping = {
    "q_2": "console.log",
    "q_4": "console.log",
    "q_18": "console.log",
    "q_19": "array",
    "q_20": "array",
    "q_23": "forEach",
    "q_24": "map",
    "q_25": "callback"
}

# 1. Update in-domain spans & paraphrasing
for q in questions:
    if q["in_domain"]:
        qid = q["id"]
        # Update primary span
        if qid in primary_spans:
            q["answer_spans"] = [primary_spans[qid]]
            
        # Add extra spans
        if qid in keyword_mapping:
            extra = find_extra_spans(keyword_mapping[qid])
            for e in extra:
                # check if overlap with primary
                overlap = False
                for existing in q["answer_spans"]:
                    if e["video_id"] == existing["video_id"]:
                        if not (e["end_seconds"] < existing["start_seconds"] or e["start_seconds"] > existing["end_seconds"]):
                            overlap = True
                if not overlap:
                    q["answer_spans"].append(e)
                    
        # Round timestamps
        for span in q["answer_spans"]:
            span["start_seconds"] = round(span["start_seconds"], 2)
            span["end_seconds"] = round(span["end_seconds"], 2)
            
        # Paraphrase
        if qid in paraphrased:
            q["question"] = paraphrased[qid]

# 2. Handle OOD questions
ood_q26 = {
    "id": "q_26",
    "question": "What is the capital of France and what is its population?",
    "video_id": None,
    "answer_spans": [],
    "ground_truth_chunk_ids": [],
    "expected_keywords": ["Paris", "France", "capital"],
    "in_domain": False,
    "note": "Unrelated. Searched 'capital', 'france'. 0 hits."
}
ood_q27 = {
    "id": "q_27",
    "question": "Who painted the Mona Lisa and in which museum is it displayed?",
    "video_id": None,
    "answer_spans": [],
    "ground_truth_chunk_ids": [],
    "expected_keywords": ["Mona Lisa", "Da Vinci", "Louvre"],
    "in_domain": False,
    "note": "Unrelated. Searched 'mona lisa', 'louvre'. 0 hits."
}
ood_q28 = {
    "id": "q_28",
    "question": "How do I manage state with React hooks like useState?",
    "video_id": None,
    "answer_spans": [],
    "ground_truth_chunk_ids": [],
    "expected_keywords": ["react", "hook", "useState", "state"],
    "in_domain": False,
    "note": "Searched 'react', 'hook'. 0 hits. Genuinely absent."
}
ood_q29 = {
    "id": "q_29",
    "question": "What is the purpose of a Python decorator?",
    "video_id": None,
    "answer_spans": [],
    "ground_truth_chunk_ids": [],
    "expected_keywords": ["python", "decorator", "function"],
    "in_domain": False,
    "note": "Searched 'python', 'decorator'. 0 hits. Genuinely absent."
}
ood_q30 = {
    "id": "q_30",
    "question": "Can you explain the difference between INNER JOIN and LEFT JOIN in SQL?",
    "video_id": None,
    "answer_spans": [],
    "ground_truth_chunk_ids": [],
    "expected_keywords": ["sql", "join", "inner", "left"],
    "in_domain": False,
    "note": "Searched 'sql', 'join'. 0 hits. Genuinely absent."
}

for i in range(len(questions)):
    if questions[i]["id"] == "q_26": questions[i] = ood_q26
    if questions[i]["id"] == "q_27": questions[i] = ood_q27
    if questions[i]["id"] == "q_28": questions[i] = ood_q28
    if questions[i]["id"] == "q_29": questions[i] = ood_q29
    if questions[i]["id"] == "q_30": questions[i] = ood_q30

# Write to file
with open("eval/golden_questions/starter_set.json", "w") as f:
    json.dump(questions, f, indent=2)

# Generate validation printout
validation = "### Validation Table\n"
for q in questions:
    validation += f"**{q['id']}**: {q['question']}\n"
    if q['in_domain']:
        for i, span in enumerate(q['answer_spans']):
            cursor.execute("SELECT text_english FROM transcript_segments WHERE video_id = ? AND start_seconds >= ? AND end_seconds <= ? ORDER BY start_seconds", (span['video_id'], max(0, span['start_seconds'] - 20), span['end_seconds'] + 20))
            texts = [r['text_english'] for r in cursor.fetchall()]
            context = " ".join(texts)
            validation += f"  - Span {i+1}: {span['video_id']} [{span['start_seconds']:.2f} - {span['end_seconds']:.2f}]\n"
            validation += f"    Context (+/- 20s): {context[:100]}...\n"
    else:
        validation += f"  - OOD Note: {q.get('note', '')}\n"
    validation += "\n"

with open("scratch_media/validation.md", "w") as f:
    f.write(validation)

print("Updated starter_set.json and generated validation.md")
