import sys
sys.path.append('.')
from videoqa.core.retriever import retrieve

print("=== Query: What is forEach? ===")
try:
    res1 = retrieve("What is forEach?")
    print("Answer:")
    print(res1["answer"])
    print("Citations:")
    for c in res1["citations"]:
        print(f"[{c.get('similarity', 0):.4f}] {c.get('chunk_id')}: {c.get('text', '')[:50]}...")
except Exception as e:
    print(f"Error: {e}")

print("\n=== Query: What is the capital of France? ===")
try:
    res2 = retrieve("What is the capital of France?")
    if res2["answer"] == "I couldn't find relevant content in this video for your question.":
        print("Retriever correctly abstained (returned canned response).")
    else:
        print("Retriever did NOT abstain.")
        print(res2["answer"])
except Exception as e:
    print(f"Error: {e}")
