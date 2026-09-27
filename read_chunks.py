import requests
import os
import json

def create_embedding(text):
    r = requests.post("http://localhost:11434/api/embeddings", json={
        "model": "bge-m3",
        "prompt": text
    })

    embedding = r.json()['embedding']
    return embedding

# a = create_embedding("Cat sat on Mat")
# print(a)

jsons = os.listdir("jsons")
print(jsons)
my_dict = []
chunk_id = 0

for json in jsons:
    with open(os.path.join("jsons", json), "r") as f:
        content = json.load(f)
    for chunk in content['chunks']:
        print(chunk)
        chunk['chunk_id'] = chunk_id
        chunk['embedding'] = create_embedding(chunk['text'])
        my_dict.append(chunk)
        chunk_id += 1
    break

print(my_dict)