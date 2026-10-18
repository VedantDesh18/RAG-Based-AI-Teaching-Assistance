from unittest.mock import patch
import pytest
from fastapi.testclient import TestClient
from pathlib import Path

from videoqa.config import config
from videoqa.db.sqlite import insert_chunks, insert_transcript_segments, run_migrations, upsert_video


@pytest.fixture()
def test_client(tmp_path):
    original_db = config['paths']['db']
    original_chroma = config['paths']['chroma']
    original_media = config['paths'].get('media')
    original_legacy = config['paths'].get('legacy_media')

    config['paths']['db'] = str(tmp_path / 'videoqa.db')
    config['paths']['chroma'] = str(tmp_path / 'chroma')
    config['paths']['media'] = str(tmp_path / 'media')
    config['paths']['legacy_media'] = str(tmp_path / 'videos')
    Path(config['paths']['media']).mkdir(parents=True, exist_ok=True)
    Path(config['paths']['legacy_media']).mkdir(parents=True, exist_ok=True)
    run_migrations()

    from videoqa.main import app
    with TestClient(app) as client:
        yield client

    config['paths']['db'] = original_db
    config['paths']['chroma'] = original_chroma
    if original_media is None:
        config['paths'].pop('media', None)
    else:
        config['paths']['media'] = original_media
    if original_legacy is None:
        config['paths'].pop('legacy_media', None)
    else:
        config['paths']['legacy_media'] = original_legacy


class FakeStreamResponse:
    def __init__(self, text="The video explains async callbacks."):
        self.text = text

    def raise_for_status(self):
        return None

    def iter_lines(self):
        return [f'{{"response":"{self.text}"}}'.encode('utf-8')]


# Test 1: Ready local video with actual indexed chunks: input enabled / query eligible
def test_ready_local_video_with_actual_indexed_chunks(test_client):
    video_id = "local-ready-v1"
    upsert_video({
        "id": "row-ready-1",
        "video_id": video_id,
        "source_type": "file_upload",
        "title": "Local Javascript Tutorial",
        "duration_seconds": 300,
        "status": "ready",
        "created_at": "2026-10-18T12:00:00+00:00",
        "updated_at": "2026-10-18T12:00:00+00:00",
    })
    insert_chunks([{
        "chunk_id": "chunk-1",
        "video_id": video_id,
        "chunk_index": 0,
        "start_seconds": 10.0,
        "end_seconds": 25.0,
        "text": "Callbacks are functions passed as arguments.",
        "text_original": "Callbacks are functions passed as arguments.",
        "word_count": 6,
        "language": "en",
    }])

    detail = test_client.get(f"/api/videos/{video_id}")
    assert detail.status_code == 200
    data = detail.json()
    assert data["status"] == "ready"
    assert data["chunk_count"] == 1

    with patch("videoqa.api.query.create_embedding", return_value=[[0.1] * 1024]), \
         patch("videoqa.api.query.search_vectors", return_value=[{
             "chunk_id": "chunk-1", "video_id": video_id, "title": "Local Javascript Tutorial",
             "start_seconds": 10.0, "end_seconds": 25.0, "text": "Callbacks are functions passed as arguments.",
             "similarity": 0.95,
         }]), \
         patch("videoqa.api.query.requests.post", return_value=FakeStreamResponse()):
        query_res = test_client.post("/api/query", json={"question": "What is a callback?", "video_id": video_id})
        assert query_res.status_code == 200
        assert "Callbacks are functions passed as arguments." in query_res.text


# Test 2: Ready video with stale chunk_count in DB row but real chunks: input enabled
def test_ready_video_with_stale_chunk_count_in_db(test_client):
    video_id = "local-stale-v2"
    # Insert row with stale chunk_count = 0
    upsert_video({
        "id": "row-stale-2",
        "video_id": video_id,
        "source_type": "file_upload",
        "title": "Stale Count Video",
        "duration_seconds": 150,
        "chunk_count": 0,
        "status": "ready",
        "created_at": "2026-10-18T12:00:00+00:00",
        "updated_at": "2026-10-18T12:00:00+00:00",
    })
    insert_chunks([{
        "chunk_id": "chunk-stale-1",
        "video_id": video_id,
        "chunk_index": 0,
        "start_seconds": 5.0,
        "end_seconds": 15.0,
        "text": "Stale video content that is actually indexed.",
        "text_original": "Stale video content that is actually indexed.",
        "word_count": 7,
        "language": "en",
    }])

    # Detail API must return actual chunk count, not the stale 0
    detail = test_client.get(f"/api/videos/{video_id}")
    assert detail.status_code == 200
    assert detail.json()["chunk_count"] == 1

    # Query endpoint must allow querying
    with patch("videoqa.api.query.create_embedding", return_value=[[0.1] * 1024]), \
         patch("videoqa.api.query.search_vectors", return_value=[{
             "chunk_id": "chunk-stale-1", "video_id": video_id, "title": "Stale Count Video",
             "start_seconds": 5.0, "end_seconds": 15.0, "text": "Stale video content that is actually indexed.",
             "similarity": 0.92,
         }]), \
         patch("videoqa.api.query.requests.post", return_value=FakeStreamResponse()):
        query_res = test_client.post("/api/query", json={"question": "What is in the video?", "video_id": video_id})
        assert query_res.status_code == 200


# Test 3: Video with no indexed chunks: correct unavailable state (409)
def test_video_with_no_indexed_chunks_returns_unavailable(test_client):
    video_id = "local-empty-v3"
    upsert_video({
        "id": "row-empty-3",
        "video_id": video_id,
        "source_type": "file_upload",
        "title": "Unindexed Video",
        "duration_seconds": 60,
        "chunk_count": 0,
        "status": "ready",
        "created_at": "2026-10-18T12:00:00+00:00",
        "updated_at": "2026-10-18T12:00:00+00:00",
    })

    detail = test_client.get(f"/api/videos/{video_id}")
    assert detail.status_code == 200
    assert detail.json()["chunk_count"] == 0

    # Query should be rejected with 409 Conflict
    query_res = test_client.post("/api/query", json={"question": "Any content?", "video_id": video_id})
    assert query_res.status_code == 409
    assert "transcript chunks are indexed" in query_res.json()["detail"]


# Test 4: Failed indexing: error shown and player remains usable
def test_failed_indexing_leaves_player_usable(test_client):
    video_id = "local-failed-v4"
    # Create actual media file on disk
    media_dir = Path(config["paths"]["media"])
    test_file = media_dir / f"{video_id}.mp4"
    test_file.write_bytes(b"\x00\x00\x00\x18ftypmp42\x00\x00\x00\x00mp42isom" + b"\x00" * 200)

    upsert_video({
        "id": "row-failed-4",
        "video_id": video_id,
        "source_type": "file_upload",
        "title": "Failed Ingestion Video",
        "file_path": f"media/{video_id}.mp4",
        "duration_seconds": 45,
        "status": "failed",
        "error_message": "Whisper transcription failed during audio decoding",
        "created_at": "2026-10-18T12:00:00+00:00",
        "updated_at": "2026-10-18T12:00:00+00:00",
    })

    detail = test_client.get(f"/api/videos/{video_id}")
    assert detail.status_code == 200
    data = detail.json()
    assert data["status"] == "failed"
    assert data["error_message"] == "Whisper transcription failed during audio decoding"
    assert data["media_available"] is True
    assert data["media_url"] == f"/api/videos/{video_id}/media"

    # Media endpoint must stream the video file
    media_res = test_client.get(f"/api/videos/{video_id}/media")
    assert media_res.status_code == 200
    assert len(media_res.content) == len(test_file.read_bytes())


# Test 5: Selected video ID passed correctly to the backend
def test_selected_video_id_passed_correctly_to_retrieval(test_client):
    video_id = "local-target-v5"
    other_video_id = "local-other-v5"
    for vid in [video_id, other_video_id]:
        upsert_video({
            "id": f"row-{vid}",
            "video_id": vid,
            "source_type": "file_upload",
            "title": f"Video {vid}",
            "duration_seconds": 100,
            "status": "ready",
            "created_at": "2026-10-18T12:00:00+00:00",
            "updated_at": "2026-10-18T12:00:00+00:00",
        })
        insert_chunks([{
            "chunk_id": f"chunk-{vid}-1",
            "video_id": vid,
            "chunk_index": 0,
            "start_seconds": 0,
            "end_seconds": 10,
            "text": f"Content for {vid}",
            "text_original": f"Content for {vid}",
            "word_count": 3,
            "language": "en",
        }])

    with patch("videoqa.api.query.create_embedding", return_value=[[0.1] * 1024]), \
         patch("videoqa.api.query.search_vectors", return_value=[]) as mock_search, \
         patch("videoqa.api.query.requests.post", return_value=FakeStreamResponse("General answer")):
        res = test_client.post("/api/query", json={"question": "Find in target", "video_id": video_id})
        assert res.status_code == 200
        # Assert vector search was scoped strictly to video_id
        assert mock_search.call_args.kwargs["video_id"] == video_id


# Test 6: Enter-key / POST query submission
def test_enter_key_submission_creates_chat_session(test_client):
    video_id = "local-submit-v6"
    upsert_video({
        "id": "row-submit-6",
        "video_id": video_id,
        "source_type": "file_upload",
        "title": "Submission Video",
        "duration_seconds": 60,
        "status": "ready",
        "created_at": "2026-10-18T12:00:00+00:00",
        "updated_at": "2026-10-18T12:00:00+00:00",
    })
    insert_chunks([{
        "chunk_id": "chunk-sub-1",
        "video_id": video_id,
        "chunk_index": 0,
        "start_seconds": 0,
        "end_seconds": 10,
        "text": "Answer about promises",
        "text_original": "Answer about promises",
        "word_count": 3,
        "language": "en",
    }])

    with patch("videoqa.api.query.create_embedding", return_value=[[0.1] * 1024]), \
         patch("videoqa.api.query.search_vectors", return_value=[{
             "chunk_id": "chunk-sub-1", "video_id": video_id, "title": "Submission Video",
             "start_seconds": 0.0, "end_seconds": 10.0, "text": "Answer about promises",
             "similarity": 0.9,
         }]), \
         patch("videoqa.api.query.requests.post", return_value=FakeStreamResponse("Promises represent future values.")):
        res = test_client.post("/api/query", json={"question": "How do promises work?", "video_id": video_id})
        assert res.status_code == 200
        assert "Promises represent future values." in res.text

    # Verify session and messages were stored in SQLite
    chats = test_client.get("/api/chats").json()
    assert chats["total"] >= 1
    session_id = chats["sessions"][0]["session_id"]
    chat_detail = test_client.get(f"/api/chats/{session_id}").json()
    assert len(chat_detail["messages"]) == 2
    assert chat_detail["messages"][0]["role"] == "user"
    assert chat_detail["messages"][0]["content"] == "How do promises work?"
    assert chat_detail["messages"][1]["role"] == "assistant"


# Test 7: Send-button submission with streaming tokens and citations
def test_send_button_submission_streams_tokens_and_citations(test_client):
    video_id = "local-stream-v7"
    upsert_video({
        "id": "row-stream-7",
        "video_id": video_id,
        "source_type": "file_upload",
        "title": "Event Loop",
        "duration_seconds": 120,
        "status": "ready",
        "created_at": "2026-10-18T12:00:00+00:00",
        "updated_at": "2026-10-18T12:00:00+00:00",
    })
    insert_chunks([{
        "chunk_id": "chunk-el-1",
        "video_id": video_id,
        "chunk_index": 0,
        "start_seconds": 15.0,
        "end_seconds": 30.0,
        "text": "The event loop monitors the call stack and callback queue.",
        "text_original": "The event loop monitors the call stack and callback queue.",
        "word_count": 10,
        "language": "en",
    }])

    with patch("videoqa.api.query.create_embedding", return_value=[[0.1] * 1024]), \
         patch("videoqa.api.query.search_vectors", return_value=[{
             "chunk_id": "chunk-el-1", "video_id": video_id, "title": "Event Loop",
             "start_seconds": 15.0, "end_seconds": 30.0,
             "text": "The event loop monitors the call stack and callback queue.",
             "similarity": 0.88,
         }]), \
         patch("videoqa.api.query.requests.post", return_value=FakeStreamResponse("The event loop runs callbacks.")):
        res = test_client.post("/api/query", json={"question": "What is the event loop?", "video_id": video_id})
        assert res.status_code == 200
        assert "event: meta" in res.text
        assert "event: token" in res.text
        assert "event: done" in res.text
        assert '"start_display": "00:15"' in res.text


# Test 8: API failure followed by successful retry
def test_api_failure_followed_by_successful_retry(test_client):
    video_id = "local-retry-v8"
    upsert_video({
        "id": "row-retry-8",
        "video_id": video_id,
        "source_type": "file_upload",
        "title": "Robust Video",
        "duration_seconds": 60,
        "status": "ready",
        "created_at": "2026-10-18T12:00:00+00:00",
        "updated_at": "2026-10-18T12:00:00+00:00",
    })
    insert_chunks([{
        "chunk_id": "chunk-rob-1",
        "video_id": video_id,
        "chunk_index": 0,
        "start_seconds": 0,
        "end_seconds": 10,
        "text": "Content is ready.",
        "text_original": "Content is ready.",
        "word_count": 3,
        "language": "en",
    }])

    import requests as req

    # First attempt: Ollama service fails with RequestException
    with patch("videoqa.api.query.create_embedding", side_effect=req.RequestException("Ollama offline")):
        failed_res = test_client.post("/api/query", json={"question": "Test question", "video_id": video_id})
        assert failed_res.status_code == 200
        assert "event: error" in failed_res.text
        assert "local AI service is unavailable" in failed_res.text

    # Second attempt: Ollama service recovered, query succeeds
    with patch("videoqa.api.query.create_embedding", return_value=[[0.1] * 1024]), \
         patch("videoqa.api.query.search_vectors", return_value=[]), \
         patch("videoqa.api.query.requests.post", return_value=FakeStreamResponse("Recovered answer")):
        success_res = test_client.post("/api/query", json={"question": "Test question retry", "video_id": video_id})
        assert success_res.status_code == 200
        assert "Recovered answer" in success_res.text


# Test 9: No regression for YouTube videos
def test_no_regression_for_youtube_videos(test_client):
    video_id = "dQw4w9WgXcQ"
    upsert_video({
        "id": "row-yt-9",
        "video_id": video_id,
        "source_type": "youtube",
        "source_url": f"https://www.youtube.com/watch?v={video_id}",
        "title": "Never Gonna Give You Up",
        "channel": "RickAstleyVEVO",
        "duration_seconds": 213,
        "thumbnail_url": f"https://i.ytimg.com/vi/{video_id}/hqdefault.jpg",
        "status": "ready",
        "created_at": "2026-10-18T12:00:00+00:00",
        "updated_at": "2026-10-18T12:00:00+00:00",
    })
    insert_chunks([{
        "chunk_id": "chunk-yt-1",
        "video_id": video_id,
        "chunk_index": 0,
        "start_seconds": 43.0,
        "end_seconds": 55.0,
        "text": "Never gonna give you up, never gonna let you down.",
        "text_original": "Never gonna give you up, never gonna let you down.",
        "word_count": 10,
        "language": "en",
    }])

    detail = test_client.get(f"/api/videos/{video_id}")
    assert detail.status_code == 200
    yt_data = detail.json()
    assert yt_data["source_type"] == "youtube"
    assert yt_data["media_available"] is True
    # YouTube videos don't have local media_url
    assert "media_url" not in yt_data

    # Query YouTube video
    with patch("videoqa.api.query.create_embedding", return_value=[[0.1] * 1024]), \
         patch("videoqa.api.query.search_vectors", return_value=[{
             "chunk_id": "chunk-yt-1", "video_id": video_id, "title": "Never Gonna Give You Up",
             "start_seconds": 43.0, "end_seconds": 55.0,
             "text": "Never gonna give you up, never gonna let you down.",
             "similarity": 0.99,
         }]), \
         patch("videoqa.api.query.requests.post", return_value=FakeStreamResponse("Rick Astley sings his iconic song.")):
        res = test_client.post("/api/query", json={"question": "What is the chorus?", "video_id": video_id})
        assert res.status_code == 200
        assert "event: done" in res.text
        # Verified YouTube deeplink generated from trusted database data
        assert f"https://youtu.be/{video_id}?t=43" in res.text
