import requests
from videoqa.config import config

def generate_response(prompt: str) -> str:
    r = requests.post(f"{config['ollama_url']}/api/generate", json={
        "model": config['model_names']['llm'],
        "prompt": prompt,
        "stream": False
    })
    response = r.json()
    return response.get("response", "")
