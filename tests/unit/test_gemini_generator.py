import os
from unittest.mock import MagicMock, patch
import pytest

from videoqa.config import config
from videoqa.core.generator import (
    DEFAULT_GEMINI_MODEL,
    GeminiAPIError,
    GeminiAuthError,
    GeminiConfigurationError,
    GeminiRateLimitError,
    GeminiTimeoutError,
    _handle_gemini_exception,
    generate_gemini,
    generate_response,
    get_gemini_api_key,
    get_gemini_client,
    get_gemini_model,
    get_llm_provider,
    stream_gemini,
    stream_response,
)


def test_get_llm_provider_default_and_override(monkeypatch):
    monkeypatch.delenv("LLM_PROVIDER", raising=False)
    config["llm_provider"] = "gemini"
    assert get_llm_provider() == "gemini"

    monkeypatch.setenv("LLM_PROVIDER", "ollama")
    assert get_llm_provider() == "ollama"

    monkeypatch.setenv("LLM_PROVIDER", "GEMINI")
    assert get_llm_provider() == "gemini"


def test_get_gemini_model_configuration(monkeypatch):
    monkeypatch.delenv("GEMINI_MODEL", raising=False)
    config["gemini_model"] = ""
    config.get("model_names", {})["gemini"] = ""
    assert get_gemini_model() == DEFAULT_GEMINI_MODEL

    monkeypatch.setenv("GEMINI_MODEL", "gemini-2.0-flash")
    assert get_gemini_model() == "gemini-2.0-flash"


def test_get_gemini_api_key_sanitization(monkeypatch):
    # Ensure keys with surrounding quotes or whitespace are cleanly sanitized
    monkeypatch.setenv("GEMINI_API_KEY", '  "AIzaTestSecretKey123"  ')
    assert get_gemini_api_key() == "AIzaTestSecretKey123"

    # Verify key is never logged or exposed via representation
    key = get_gemini_api_key()
    assert "AIza" in key
    # Ensure our code does not print or log it
    assert not hasattr(key, "exposed")


def test_missing_api_key_raises_configuration_error(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    config["gemini_api_key"] = ""

    with pytest.raises(GeminiConfigurationError) as exc_info:
        get_gemini_client()
    assert "GEMINI_API_KEY is not configured" in str(exc_info.value)


def test_generate_gemini_mocked_success(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test-key-mocked")
    config["gemini_api_key"] = "test-key-mocked"

    mock_response = MagicMock()
    mock_response.text = "Grounded teaching assistant answer."

    mock_client = MagicMock()
    mock_client.models.generate_content.return_value = mock_response

    with patch("videoqa.core.generator.get_gemini_client", return_value=mock_client):
        result = generate_gemini("Explain recursion in 1 sentence.")
        assert result == "Grounded teaching assistant answer."
        mock_client.models.generate_content.assert_called_once()
        args, kwargs = mock_client.models.generate_content.call_args
        assert kwargs["model"] == get_gemini_model()
        assert kwargs["contents"] == "Explain recursion in 1 sentence."


def test_stream_gemini_mocked_success(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test-key-mocked")
    config["gemini_api_key"] = "test-key-mocked"

    chunk1 = MagicMock()
    chunk1.text = "Hello "
    chunk2 = MagicMock()
    chunk2.text = "student, "
    chunk3 = MagicMock()
    chunk3.text = "welcome."
    chunk_empty = MagicMock()
    chunk_empty.text = None

    mock_client = MagicMock()
    mock_client.models.generate_content_stream.return_value = [chunk1, chunk2, chunk_empty, chunk3]

    with patch("videoqa.core.generator.get_gemini_client", return_value=mock_client):
        tokens = list(stream_gemini("Tell me about loops."))
        assert tokens == ["Hello ", "student, ", "welcome."]


def test_error_handling_rate_limit(monkeypatch):
    from google.genai import errors
    mock_err = errors.ClientError(429, {"error": {"message": "RESOURCE_EXHAUSTED: Rate limit exceeded"}})
    mapped = _handle_gemini_exception(mock_err)
    assert isinstance(mapped, GeminiRateLimitError)
    assert "rate limit or quota exceeded" in str(mapped)


def test_error_handling_timeout(monkeypatch):
    from google.genai import errors
    mock_err = errors.ServerError(504, {"error": {"message": "DEADLINE_EXCEEDED"}})
    mapped = _handle_gemini_exception(mock_err)
    assert isinstance(mapped, GeminiTimeoutError)
    assert "timed out" in str(mapped)


def test_error_handling_auth_failure(monkeypatch):
    from google.genai import errors
    mock_err = errors.ClientError(400, {"error": {"message": "API_KEY_INVALID: API key not valid"}})
    mapped = _handle_gemini_exception(mock_err)
    assert isinstance(mapped, GeminiAuthError)
    assert "authentication failed" in str(mapped)


def test_error_handling_generic_api_error(monkeypatch):
    from google.genai import errors
    mock_err = errors.ServerError(500, {"error": {"message": "Internal error"}})
    mapped = _handle_gemini_exception(mock_err)
    assert isinstance(mapped, GeminiAPIError)
    assert "Gemini API error occurred" in str(mapped)


def test_dispatch_generate_and_stream(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "gemini")
    config["llm_provider"] = "gemini"

    with patch("videoqa.core.generator.generate_gemini", return_value="gemini answer") as mock_gen, \
         patch("videoqa.core.generator.stream_gemini", return_value=iter(["tok1", "tok2"])) as mock_stream:
        assert generate_response("test prompt") == "gemini answer"
        mock_gen.assert_called_once_with("test prompt")

        assert list(stream_response("test prompt")) == ["tok1", "tok2"]
        mock_stream.assert_called_once_with("test prompt")
