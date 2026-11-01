import json
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest
from fastapi.testclient import TestClient

from videoqa.config import config
from videoqa.core.generator import (
    GeminiAuthError,
    GeminiRateLimitError,
    GeminiTimeoutError,
)
from videoqa.db.sqlite import insert_chunks, run_migrations, upsert_video


@pytest.fixture()
def test_client(tmp_path):
    original_db = config['paths']['db']
    original_chroma = config['paths']['chroma']
    original_media = config['paths'].get('media')
    original_legacy = config['paths'].get('legacy_media')
    original_provider = config.get('llm_provider')
    original_key = config.get('gemini_api_key')

    config['paths']['db'] = str(tmp_path / 'videoqa.db')
    config['paths']['chroma'] = str(tmp_path / 'chroma')
    config['paths']['media'] = str(tmp_path / 'media')
    config['paths']['legacy_media'] = str(tmp_path / 'videos')
    config['llm_provider'] = 'gemini'
    Path(config['paths']['media']).mkdir(parents=True, exist_ok=True)
    Path(config['paths']['legacy_media']).mkdir(parents=True, exist_ok=True)
    run_migrations()

    from videoqa.main import app
    with TestClient(app) as client:
        yield client

    config['paths']['db'] = original_db
    config['paths']['chroma'] = original_chroma
    if original_provider is None:
        config.pop('llm_provider', None)
    else:
        config['llm_provider'] = original_provider
    if original_key is None:
        config.pop('gemini_api_key', None)
    else:
        config['gemini_api_key'] = original_key
    if original_media is None:
        config['paths'].pop('media', None)
    else:
        config['paths']['media'] = original_media
    if original_legacy is None:
        config['paths'].pop('legacy_media', None)
    else:
        config['paths']['legacy_media'] = original_legacy


def test_missing_api_key_returns_safe_sse_error(test_client, monkeypatch):
    video_id = "gemini-video-nokey"
    upsert_video({
        "id": "row-nokey-1",
        "video_id": video_id,
        "source_type": "file_upload",
        "title": "Machine Learning Intro",
        "duration_seconds": 120,
        "status": "ready",
        "created_at": "2026-10-25T10:00:00+00:00",
        "updated_at": "2026-10-25T10:00:00+00:00",
    })
    insert_chunks([{
        "chunk_id": "chunk-nokey-1",
        "video_id": video_id,
        "chunk_index": 0,
        "start_seconds": 0.0,
        "end_seconds": 15.0,
        "text": "Machine learning uses algorithms to learn from data.",
        "text_original": "Machine learning uses algorithms to learn from data.",
        "word_count": 8,
        "language": "en",
    }])

    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    config["gemini_api_key"] = ""

    with patch("videoqa.api.query.create_embedding", return_value=[[0.1] * 1024]), \
         patch("videoqa.api.query.search_vectors", return_value=[{
             "chunk_id": "chunk-nokey-1", "video_id": video_id, "title": "Machine Learning Intro",
             "start_seconds": 0.0, "end_seconds": 15.0,
             "text": "Machine learning uses algorithms to learn from data.",
             "similarity": 0.92,
         }]):
        res = test_client.post("/api/query", json={"question": "What is machine learning?", "video_id": video_id})
        assert res.status_code == 200
        assert "event: error" in res.text
        assert "Gemini API key is not configured" in res.text
        # Ensure credentials or private tokens are not revealed
        assert "AIza" not in res.text


def test_mocked_gemini_streaming_preserves_citations_and_sse_contract(test_client, monkeypatch):
    video_id = "gemini-video-stream"
    upsert_video({
        "id": "row-stream-1",
        "video_id": video_id,
        "source_type": "youtube",
        "source_url": f"https://www.youtube.com/watch?v={video_id}",
        "title": "React Hooks Overview",
        "duration_seconds": 180,
        "status": "ready",
        "created_at": "2026-10-25T10:00:00+00:00",
        "updated_at": "2026-10-25T10:00:00+00:00",
    })
    insert_chunks([{
        "chunk_id": "chunk-rh-1",
        "video_id": video_id,
        "chunk_index": 0,
        "start_seconds": 12.0,
        "end_seconds": 28.0,
        "text": "useState lets you add state to functional components.",
        "text_original": "useState lets you add state to functional components.",
        "word_count": 8,
        "language": "en",
    }])

    monkeypatch.setenv("GEMINI_API_KEY", "mock-gemini-key")
    config["gemini_api_key"] = "mock-gemini-key"

    recorded_prompts = []

    def fake_stream_gemini(prompt: str):
        recorded_prompts.append(prompt)
        yield "React "
        yield "hooks "
        yield "manage "
        yield "state."

    with patch("videoqa.api.query.create_embedding", return_value=[[0.1] * 1024]), \
         patch("videoqa.api.query.search_vectors", return_value=[{
             "chunk_id": "chunk-rh-1", "video_id": video_id, "title": "React Hooks Overview",
             "start_seconds": 12.0, "end_seconds": 28.0,
             "text": "useState lets you add state to functional components.",
             "similarity": 0.94,
         }]), \
         patch("videoqa.api.query.stream_response", side_effect=fake_stream_gemini):
        res = test_client.post("/api/query", json={"question": "How does useState work?", "video_id": video_id})
        assert res.status_code == 200

        # Verify SSE event protocol and streamed tokens
        assert "event: meta" in res.text
        assert "event: token" in res.text
        assert 'data: {"text": "React "}' in res.text
        assert 'data: {"text": "hooks "}' in res.text
        assert 'data: {"text": "manage "}' in res.text
        assert 'data: {"text": "state."}' in res.text
        assert "event: done" in res.text

        # Verify assembled message was persisted in database
        chats = test_client.get("/api/chats").json()
        assert chats["total"] >= 1
        session_id = chats["sessions"][0]["session_id"]
        chat_detail = test_client.get(f"/api/chats/{session_id}").json()
        assert any(m["role"] == "assistant" and m["content"] == "React hooks manage state." for m in chat_detail["messages"])

        # Verify ground truth citations rendered from database metadata (not invented by model)
        assert '"start_display": "00:12"' in res.text
        assert '"end_display": "00:28"' in res.text
        assert f"https://youtu.be/{video_id}?t=12" in res.text

        # Verify prompt passed to Gemini contains video ID, title, and timestamps
        assert len(recorded_prompts) == 1
        prompt = recorded_prompts[0]
        assert f"Video ID: {video_id}" in prompt
        assert "React Hooks Overview" in prompt
        assert "00:12" in prompt


def test_gemini_timeout_handling_in_query(test_client, monkeypatch):
    video_id = "gemini-video-timeout"
    upsert_video({
        "id": "row-timeout-1",
        "video_id": video_id,
        "source_type": "file_upload",
        "title": "Timeout Video",
        "duration_seconds": 60,
        "status": "ready",
        "created_at": "2026-10-25T10:00:00+00:00",
        "updated_at": "2026-10-25T10:00:00+00:00",
    })
    insert_chunks([{
        "chunk_id": "chunk-to-1",
        "video_id": video_id,
        "chunk_index": 0,
        "start_seconds": 0.0,
        "end_seconds": 10.0,
        "text": "Testing timeout handling.",
        "text_original": "Testing timeout handling.",
        "word_count": 3,
        "language": "en",
    }])

    monkeypatch.setenv("GEMINI_API_KEY", "mock-gemini-key")
    config["gemini_api_key"] = "mock-gemini-key"

    def timeout_stream(prompt: str):
        raise GeminiTimeoutError("Gemini API request timed out. Please try again.")

    with patch("videoqa.api.query.create_embedding", return_value=[[0.1] * 1024]), \
         patch("videoqa.api.query.search_vectors", return_value=[{
             "chunk_id": "chunk-to-1", "video_id": video_id, "title": "Timeout Video",
             "start_seconds": 0.0, "end_seconds": 10.0,
             "text": "Testing timeout handling.",
             "similarity": 0.9,
         }]), \
         patch("videoqa.api.query.stream_response", side_effect=timeout_stream):
        res = test_client.post("/api/query", json={"question": "Timeout test", "video_id": video_id})
        assert res.status_code == 200
        assert "event: error" in res.text
        assert "Gemini API request timed out" in res.text


def test_gemini_rate_limit_handling_in_query(test_client, monkeypatch):
    video_id = "gemini-video-ratelimit"
    upsert_video({
        "id": "row-rl-1",
        "video_id": video_id,
        "source_type": "file_upload",
        "title": "Rate Limit Video",
        "duration_seconds": 60,
        "status": "ready",
        "created_at": "2026-10-25T10:00:00+00:00",
        "updated_at": "2026-10-25T10:00:00+00:00",
    })
    insert_chunks([{
        "chunk_id": "chunk-rl-1",
        "video_id": video_id,
        "chunk_index": 0,
        "start_seconds": 0.0,
        "end_seconds": 10.0,
        "text": "Testing rate limit handling.",
        "text_original": "Testing rate limit handling.",
        "word_count": 4,
        "language": "en",
    }])

    monkeypatch.setenv("GEMINI_API_KEY", "mock-gemini-key")
    config["gemini_api_key"] = "mock-gemini-key"

    def ratelimit_stream(prompt: str):
        raise GeminiRateLimitError("Gemini API rate limit or quota exceeded. Please wait a moment and try again.")

    with patch("videoqa.api.query.create_embedding", return_value=[[0.1] * 1024]), \
         patch("videoqa.api.query.search_vectors", return_value=[{
             "chunk_id": "chunk-rl-1", "video_id": video_id, "title": "Rate Limit Video",
             "start_seconds": 0.0, "end_seconds": 10.0,
             "text": "Testing rate limit handling.",
             "similarity": 0.9,
         }]), \
         patch("videoqa.api.query.stream_response", side_effect=ratelimit_stream):
        res = test_client.post("/api/query", json={"question": "Rate limit test", "video_id": video_id})
        assert res.status_code == 200
        assert "event: error" in res.text
        assert "Gemini API rate limit or quota exceeded" in res.text


def test_gemini_auth_failure_handling_in_query(test_client, monkeypatch):
    video_id = "gemini-video-auth"
    upsert_video({
        "id": "row-auth-1",
        "video_id": video_id,
        "source_type": "file_upload",
        "title": "Auth Video",
        "duration_seconds": 60,
        "status": "ready",
        "created_at": "2026-10-25T10:00:00+00:00",
        "updated_at": "2026-10-25T10:00:00+00:00",
    })
    insert_chunks([{
        "chunk_id": "chunk-auth-1",
        "video_id": video_id,
        "chunk_index": 0,
        "start_seconds": 0.0,
        "end_seconds": 10.0,
        "text": "Testing auth failure handling.",
        "text_original": "Testing auth failure handling.",
        "word_count": 4,
        "language": "en",
    }])

    monkeypatch.setenv("GEMINI_API_KEY", "invalid-key")
    config["gemini_api_key"] = "invalid-key"

    def auth_stream(prompt: str):
        raise GeminiAuthError("Gemini API authentication failed. Please verify your GEMINI_API_KEY.")

    with patch("videoqa.api.query.create_embedding", return_value=[[0.1] * 1024]), \
         patch("videoqa.api.query.search_vectors", return_value=[{
             "chunk_id": "chunk-auth-1", "video_id": video_id, "title": "Auth Video",
             "start_seconds": 0.0, "end_seconds": 10.0,
             "text": "Testing auth failure handling.",
             "similarity": 0.9,
         }]), \
         patch("videoqa.api.query.stream_response", side_effect=auth_stream):
        res = test_client.post("/api/query", json={"question": "Auth test", "video_id": video_id})
        assert res.status_code == 200
        assert "event: error" in res.text
        assert "Gemini API authentication failed" in res.text
