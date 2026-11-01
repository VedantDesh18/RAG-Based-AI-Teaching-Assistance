import os
import pytest

from videoqa.config import config
from videoqa.core.generator import generate_response, get_gemini_api_key, stream_response


def has_live_gemini_key() -> bool:
    key = get_gemini_api_key()
    # A valid Gemini API key is non-empty and not a mock placeholder
    return bool(key and not key.startswith("test-") and not key.startswith("mock-") and len(key) > 10)


@pytest.mark.live_gemini
def test_real_gemini_api_smoke():
    """Live smoke test against the Google Gemini API.

    This test executes ONLY when a real GEMINI_API_KEY is configured in the environment or .env.
    It verifies live authentication, network connectivity, and streaming response delivery.
    The secret API key is never printed or logged.
    """
    if not has_live_gemini_key():
        pytest.skip("Skipping live Gemini smoke test: No real GEMINI_API_KEY configured in environment or .env.")

    # Temporarily ensure provider is gemini
    original_provider = config.get("llm_provider")
    config["llm_provider"] = "gemini"

    try:
        # Non-streaming smoke test
        prompt = "Reply with exactly the word 'OK' and nothing else."
        answer = generate_response(prompt)
        assert bool(answer.strip()), "Expected non-empty response from live Gemini API"

        # Streaming smoke test
        stream_tokens = list(stream_response("Reply with exactly 'HELLO'."))
        stream_text = "".join(stream_tokens).strip()
        assert bool(stream_text), "Expected tokens from live Gemini streaming API"
    finally:
        if original_provider is None:
            config.pop("llm_provider", None)
        else:
            config["llm_provider"] = original_provider
