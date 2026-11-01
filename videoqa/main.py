from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from videoqa.api import ingest, videos, jobs, query
from videoqa.db.sqlite import run_migrations
import videoqa.config as config_module
from videoqa.db.sqlite import get_connection
from videoqa.storage import media_root
from videoqa.vectorstore.chroma import get_collection
import importlib.util
import os
import requests
import shutil

run_migrations()

app = FastAPI(title="VideoQA API")

_default_cors_origins = (
    "http://localhost:3000,http://127.0.0.1:3000,"
    "http://localhost:3001,http://127.0.0.1:3001"
)
_cors_origins = [
    origin.strip()
    for origin in os.getenv("VIDEOQA_CORS_ORIGINS", _default_cors_origins).split(",")
    if origin.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=False,
    allow_methods=["GET", "HEAD", "POST", "DELETE"],
    allow_headers=["Accept", "Content-Type", "Range"],
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
    services = {"api": "ok"}
    try:
        conn = get_connection()
        conn.execute("SELECT 1").fetchone()
        conn.close()
        services["sqlite"] = "ok"
    except Exception:
        services["sqlite"] = "unavailable"
    try:
        get_collection().count()
        services["chroma"] = "ok"
    except Exception:
        services["chroma"] = "unavailable"
    try:
        root = media_root()
        services["media_storage"] = "ok" if root.is_dir() and os.access(root, os.R_OK | os.W_OK) else "unavailable"
    except (OSError, ValueError):
        services["media_storage"] = "unavailable"
    services["ffmpeg"] = "ok" if shutil.which("ffmpeg") else "unavailable"
    services["ffprobe"] = "ok" if shutil.which("ffprobe") else "unavailable"
    services["faster_whisper"] = "ok" if importlib.util.find_spec("faster_whisper") else "unavailable"
    services["ollama"] = "unavailable"
    services["ollama_models"] = "unavailable"
    llm_provider = config_module.config.get("llm_provider", "gemini")
    services["llm_provider"] = llm_provider
    if llm_provider == "gemini":
        has_key = bool(config_module.config.get("gemini_api_key") or os.getenv("GEMINI_API_KEY"))
        services["gemini_configured"] = "ok" if has_key else "missing_key"

    try:
        response = requests.get(f"{config_module.config['ollama_url']}/api/tags", timeout=1.5)
        if response.ok:
            services["ollama"] = "ok"
            available = {str(model.get("name", "")) for model in response.json().get("models", [])}
            if llm_provider == "ollama":
                required = {
                    config_module.config.get("model_names", {}).get("llm", ""),
                    config_module.config.get("model_names", {}).get("embedding", ""),
                }
            else:
                # When Gemini handles LLM generation, only embedding model is required in Ollama
                required = {
                    config_module.config.get("model_names", {}).get("embedding", ""),
                }
            def is_installed(model_name: str) -> bool:
                return not model_name or model_name in available or f"{model_name}:latest" in available
            services["ollama_models"] = "ok" if all(is_installed(name) for name in required) else "missing"
    except requests.RequestException:
        pass
    except (ValueError, TypeError):
        services["ollama_models"] = "unavailable"
    core = ("sqlite", "chroma", "media_storage")
    overall = "ok" if all(services[name] == "ok" for name in core) else "degraded"
    # Optional media/transcription/model services never affect the media endpoint.
    return {"status": overall, "services": services}
