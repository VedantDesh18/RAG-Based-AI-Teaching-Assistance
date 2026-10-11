import os
import yaml
from pathlib import Path

def load_config():
    config_path = Path("config.yaml")
    cfg = {}
    if config_path.exists():
        with open(config_path, "r", encoding="utf-8") as f:
            cfg = yaml.safe_load(f) or {}

    # Environment variable overrides
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

    return cfg

config = load_config()
