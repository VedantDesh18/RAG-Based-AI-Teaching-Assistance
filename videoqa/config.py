import os
import yaml
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

def load_config():
    config_path = Path("config.yaml")
    cfg = {}
    if config_path.exists():
        with open(config_path, "r", encoding="utf-8") as f:
            cfg = yaml.safe_load(f) or {}

    # Environment variable overrides
    llm_provider = os.getenv("LLM_PROVIDER")
    if llm_provider and llm_provider.strip():
        cfg["llm_provider"] = llm_provider.strip().lower()
    elif "llm_provider" not in cfg:
        cfg["llm_provider"] = "gemini"

    gemini_key = os.getenv("GEMINI_API_KEY")
    if gemini_key is not None:
        cfg["gemini_api_key"] = gemini_key.strip().strip('"\'')
    elif "gemini_api_key" not in cfg:
        cfg["gemini_api_key"] = ""

    gemini_model = os.getenv("GEMINI_MODEL")
    if gemini_model and gemini_model.strip():
        cfg["gemini_model"] = gemini_model.strip()
        if "model_names" not in cfg:
            cfg["model_names"] = {}
        cfg["model_names"]["gemini"] = gemini_model.strip()
    elif "gemini_model" not in cfg:
        cfg["gemini_model"] = cfg.get("model_names", {}).get("gemini", "gemini-2.5-flash")

    ollama_env = os.getenv("OLLAMA_URL") or os.getenv("OLLAMA_HOST")
    if ollama_env:
        if not ollama_env.startswith("http://") and not ollama_env.startswith("https://"):
            ollama_env = f"http://{ollama_env}"
        cfg["ollama_url"] = ollama_env

    if os.getenv("EMBEDDING_MODEL"):
        if "model_names" not in cfg:
            cfg["model_names"] = {}
        cfg["model_names"]["embedding"] = os.getenv("EMBEDDING_MODEL")

    if os.getenv("LLM_MODEL"):
        if "model_names" not in cfg:
            cfg["model_names"] = {}
        cfg["model_names"]["llm"] = os.getenv("LLM_MODEL")

    if os.getenv("CHROMA_PATH"):
        if "paths" not in cfg:
            cfg["paths"] = {}
        cfg["paths"]["chroma"] = os.getenv("CHROMA_PATH")

    if os.getenv("DB_PATH"):
        if "paths" not in cfg:
            cfg["paths"] = {}
        cfg["paths"]["db"] = os.getenv("DB_PATH")

    media_root = os.getenv("MEDIA_ROOT")
    legacy_media_root = os.getenv("LEGACY_MEDIA_ROOT")
    if media_root or legacy_media_root:
        if "paths" not in cfg:
            cfg["paths"] = {}
        if media_root:
            cfg["paths"]["media"] = media_root
        if legacy_media_root:
            cfg["paths"]["legacy_media"] = legacy_media_root

    return cfg

config = load_config()
