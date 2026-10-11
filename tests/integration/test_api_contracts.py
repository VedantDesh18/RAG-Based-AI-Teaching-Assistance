from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from videoqa.config import config
from videoqa.db.sqlite import run_migrations, upsert_video
from videoqa.main import app


@pytest.fixture()
def api_client(tmp_path):
    original_db = config['paths']['db']
    original_chroma = config['paths']['chroma']
    config['paths']['db'] = str(tmp_path / 'videoqa.db')
    config['paths']['chroma'] = str(tmp_path / 'chroma')
    run_migrations()
    with TestClient(app) as client:
        yield client
    config['paths']['db'] = original_db
    config['paths']['chroma'] = original_chroma


def test_url_ingest_creates_a_pollable_job_before_background_work(api_client):
    url = 'https://www.youtube.com/watch?v=dQw4w9WgXcQ'
    with patch('videoqa.api.ingest.ingest_url') as worker:
        response = api_client.post('/api/ingest/url', json={'url': url})

    assert response.status_code == 202
    body = response.json()
    assert body['job_id'] == 'dQw4w9WgXcQ'
    assert body['video_id'] == 'dQw4w9WgXcQ'
    assert body['status'] == 'queued'
    worker.assert_called_once_with(url, 'dQw4w9WgXcQ')

    status = api_client.get('/api/jobs/dQw4w9WgXcQ')
    assert status.status_code == 200
    assert status.json()['stage'] == 'queued'
    assert status.json()['stages'][0] == 'queued'


def test_library_response_has_documented_envelope_and_transcript_route(api_client):
    upsert_video({
        'id': 'video-row-1',
        'video_id': 'local-video-1',
        'source_type': 'file_upload',
        'title': 'Local meeting',
        'duration_seconds': 120,
        'status': 'ready',
        'created_at': '2026-10-05T00:00:00+00:00',
        'updated_at': '2026-10-05T00:00:00+00:00',
    })
    library = api_client.get('/api/videos')
    assert library.status_code == 200
    assert library.json()['total'] == 1
    assert library.json()['videos'][0]['video_id'] == 'local-video-1'

    transcript = api_client.get('/api/videos/local-video-1/transcript')
    assert transcript.status_code == 200
    assert transcript.json() == {'video_id': 'local-video-1', 'segments': [], 'total': 0}


def test_streamed_query_emits_structured_citations_not_model_authored_links(api_client):
    upsert_video({
        'id': 'video-row-2',
        'video_id': 'dQw4w9WgXcQ',
        'source_type': 'youtube',
        'title': 'Example lesson',
        'duration_seconds': 180,
        'status': 'ready',
        'created_at': '2026-10-05T00:00:00+00:00',
        'updated_at': '2026-10-05T00:00:00+00:00',
    })

    class FakeResponse:
        def raise_for_status(self):
            return None

        def iter_lines(self):
            return [b'{"response":"Grounded answer."}']

    chunk = {
        'chunk_id': 'chunk-1', 'video_id': 'dQw4w9WgXcQ', 'title': 'Example lesson',
        'start_seconds': 72.0, 'end_seconds': 91.0, 'text': 'Supporting transcript text.', 'similarity': .94,
    }
    with patch('videoqa.api.query.create_embedding', return_value=[[.2, .3]]), \
         patch('videoqa.api.query.search_vectors', return_value=[chunk]), \
         patch('videoqa.api.query.requests.post', return_value=FakeResponse()):
        response = api_client.post('/api/query', json={'question': 'What is covered?', 'video_id': 'dQw4w9WgXcQ'})

    assert response.status_code == 200
    assert 'event: token' in response.text
    assert 'event: done' in response.text
    assert '"start_display": "01:12"' in response.text
    assert 'youtu.be/dQw4w9WgXcQ?t=72' in response.text
