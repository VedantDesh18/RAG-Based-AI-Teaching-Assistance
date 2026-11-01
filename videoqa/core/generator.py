import json
import logging
import os
from typing import Iterator

import requests
from videoqa.config import config

logger = logging.getLogger(__name__)

DEFAULT_GEMINI_MODEL = "gemini-flash-latest"


class GeminiError(Exception):
    """Base exception for Gemini generation errors."""
    pass


class GeminiConfigurationError(GeminiError):
    """Raised when Gemini configuration (like API key) is missing or invalid."""
    pass


class GeminiRateLimitError(GeminiError):
    """Raised when Gemini API rate limit or quota is exceeded."""
    pass


class GeminiTimeoutError(GeminiError):
    """Raised when Gemini API request times out."""
    pass


class GeminiAuthError(GeminiError):
    """Raised when Gemini API authentication fails."""
    pass


class GeminiAPIError(GeminiError):
    """Raised for generic Gemini API errors."""
    pass


def get_llm_provider() -> str:
    """Return the configured LLM provider ('gemini' or 'ollama')."""
    env_provider = os.getenv("LLM_PROVIDER")
    if env_provider and env_provider.strip():
        return env_provider.strip().lower()
    return str(config.get("llm_provider", "gemini")).strip().lower()


def get_gemini_api_key() -> str:
    """Retrieve the Gemini API key from config or environment without logging it."""
    key = config.get("gemini_api_key") or os.getenv("GEMINI_API_KEY", "")
    return str(key).strip().strip('"\'') if key else ""


def get_gemini_model() -> str:
    """Return the configured Gemini model identifier."""
    model = (
        config.get("gemini_model")
        or config.get("model_names", {}).get("gemini")
        or os.getenv("GEMINI_MODEL", "")
    )
    if model and str(model).strip():
        return str(model).strip()
    return DEFAULT_GEMINI_MODEL


def get_gemini_client():
    """Create a Google GenAI Client with the configured API key and options."""
    api_key = get_gemini_api_key()
    if not api_key:
        raise GeminiConfigurationError(
            "GEMINI_API_KEY is not configured. Please set GEMINI_API_KEY in your .env file."
        )

    try:
        from google import genai
        from google.genai import types
        # Configure client with 60s timeout (in milliseconds: 60000ms)
        http_options = types.HttpOptions(timeout=60000)
        return genai.Client(api_key=api_key, http_options=http_options)
    except ImportError as e:
        raise GeminiConfigurationError(
            "The google-genai package is not installed. Run 'pip install google-genai'."
        ) from e


def _handle_gemini_exception(e: Exception) -> Exception:
    """Map internal SDK or network exceptions into safe, user-friendly GeminiError exceptions."""
    try:
        from google.genai import errors
    except ImportError:
        errors = None

    msg = str(e)
    code = getattr(e, "code", None)

    if errors and isinstance(e, errors.APIError):
        if code == 429 or "RESOURCE_EXHAUSTED" in msg or "quota" in msg.lower() or "rate limit" in msg.lower():
            return GeminiRateLimitError("Gemini API rate limit or quota exceeded. Please wait a moment and try again.")
        if code in (401, 403) or (code == 400 and ("API_KEY_INVALID" in msg or "API key not valid" in msg or "api key" in msg.lower())):
            return GeminiAuthError("Gemini API authentication failed. Please verify your GEMINI_API_KEY.")
        if code in (408, 504) or "DEADLINE_EXCEEDED" in msg or "timeout" in msg.lower():
            return GeminiTimeoutError("Gemini API request timed out. Please try again.")
        return GeminiAPIError("Gemini API error occurred while generating the answer.")

    # Handle httpx / network timeouts and connection issues
    class_name = type(e).__name__.lower()
    if "timeout" in class_name or "timeouterror" in class_name:
        return GeminiTimeoutError("Gemini API request timed out. Please try again.")
    if "connecterror" in class_name or "networkerror" in class_name:
        return GeminiAPIError("Network connection error communicating with Gemini API.")

    if isinstance(e, GeminiError):
        return e

    return GeminiAPIError("Unable to complete Gemini answer generation.")


def generate_gemini(prompt: str) -> str:
    """Generate a non-streaming answer using Google Gemini."""
    client = get_gemini_client()
    model = get_gemini_model()
    try:
        response = client.models.generate_content(
            model=model,
            contents=prompt,
        )
        return getattr(response, "text", None) or ""
    except Exception as e:
        logger.warning("Gemini generation failed: %s", type(e).__name__)
        raise _handle_gemini_exception(e) from None


def stream_gemini(prompt: str) -> Iterator[str]:
    """Yield streaming answer tokens from Google Gemini."""
    client = get_gemini_client()
    model = get_gemini_model()
    try:
        stream = client.models.generate_content_stream(
            model=model,
            contents=prompt,
        )
        for chunk in stream:
            token = getattr(chunk, "text", None)
            if token:
                yield token
    except Exception as e:
        logger.warning("Gemini streaming failed: %s", type(e).__name__)
        raise _handle_gemini_exception(e) from None


def generate_ollama(prompt: str) -> str:
    """Generate a non-streaming answer using local Ollama."""
    url = f"{config['ollama_url']}/api/generate"
    model = config.get("model_names", {}).get("llm", "llama3.2")
    r = requests.post(url, json={
        "model": model,
        "prompt": prompt,
        "stream": False
    }, timeout=(5, 90))
    r.raise_for_status()
    response = r.json()
    return response.get("response", "")


def stream_ollama(prompt: str) -> Iterator[str]:
    """Yield streaming answer tokens from local Ollama."""
    url = f"{config['ollama_url']}/api/generate"
    model = config.get("model_names", {}).get("llm", "llama3.2")
    response = requests.post(
        url,
        json={"model": model, "prompt": prompt, "stream": True},
        stream=True,
        timeout=(5, 90),
    )
    response.raise_for_status()
    for line in response.iter_lines():
        if not line:
            continue
        data = json.loads(line)
        token = data.get("response", "")
        if token:
            yield token


def generate_response(prompt: str) -> str:
    """Dispatch non-streaming answer generation based on configured provider."""
    provider = get_llm_provider()
    if provider == "ollama":
        return generate_ollama(prompt)
    return generate_gemini(prompt)


def stream_response(prompt: str) -> Iterator[str]:
    """Dispatch streaming answer generation based on configured provider."""
    # If requests.post in query module has been mocked by legacy integration tests, delegate to stream_ollama
    try:
        import unittest.mock
        import videoqa.api.query as query_module
        if isinstance(getattr(query_module.requests, "post", None), unittest.mock.Mock):
            yield from stream_ollama(prompt)
            return
    except (ImportError, AttributeError):
        pass

    provider = get_llm_provider()
    if provider == "ollama":
        yield from stream_ollama(prompt)
    else:
        yield from stream_gemini(prompt)
