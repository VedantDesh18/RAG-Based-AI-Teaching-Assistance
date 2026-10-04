import time
import requests

texts = ["This is a test sentence for embedding. " * 5] * 20

print(f"Embedding {len(texts)} chunks via Ollama bge-m3 on CPU...")
t0 = time.time()

res = requests.post("http://localhost:11434/api/embed", json={"model": "bge-m3:latest", "input": texts})

t1 = time.time()
data = res.json()
if "embeddings" in data:
    print(f"Successfully embedded {len(data['embeddings'])} chunks in {t1-t0:.2f}s")
    print(f"Time per chunk: {(t1-t0)/len(texts):.3f}s")
else:
    print("Error:", data)
