from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from videoqa.api import ingest, videos, jobs, query
from videoqa.db.sqlite import run_migrations
from videoqa.config import config
import os
import requests

run_migrations()

app = FastAPI(title="VideoQA API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[origin.strip() for origin in os.getenv(
        "VIDEOQA_CORS_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000"
    ).split(",") if origin.strip()],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(ingest.router)
app.include_router(videos.router)
app.include_router(jobs.router)
app.include_router(query.router)

@app.get("/health")
def root_health_check():
    return {"status": "healthy"}

@app.get("/api/health")
def health_check():
    services = {"api": "ok", "ollama": "unavailable"}
    try:
        response = requests.get(f"{config['ollama_url']}/api/tags", timeout=1.5)
        if response.ok:
            services["ollama"] = "ok"
    except requests.RequestException:
        pass
    # The API itself is reachable even when the local model service is stopped;
    # clients can distinguish that degraded state without treating the server as down.
    return {"status": "ok" if services["ollama"] == "ok" else "degraded", "services": services}
