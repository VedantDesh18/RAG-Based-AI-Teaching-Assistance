from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from pathlib import Path

from videoqa.config import config
from videoqa.db.sqlite import run_migrations, set_chunk_count, upsert_video


@pytest.fixture()
def api_client(tmp_path):
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
    try:
        with TestClient(app) as client:
            yield client
    finally:
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


def test_video_detail_uses_indexed_chunk_rows_not_stale_video_counter(api_client):
    from videoqa.db.sqlite import get_video, insert_chunks

    upsert_video({
        'id': 'video-row-local-ready',
        'video_id': 'local-ready-video',
        'source_type': 'file_upload',
        'title': 'Indexed local lecture',
        'duration_seconds': 60,
        'chunk_count': 0,
        'status': 'ready',
        'created_at': '2026-10-05T00:00:00+00:00',
        'updated_at': '2026-10-05T00:00:00+00:00',
    })
    insert_chunks([{
        'chunk_id': 'local-ready-chunk-1',
        'video_id': 'local-ready-video',
        'chunk_index': 0,
        'start_seconds': 12,
        'end_seconds': 20,
        'text': 'A local lecture explains indexed database queries.',
        'text_original': 'A local lecture explains indexed database queries.',
        'word_count': 7,
        'language': 'en',
    }])

    detail = api_client.get('/api/videos/local-ready-video')
    assert detail.status_code == 200
    assert detail.json()['status'] == 'ready'
    assert detail.json()['chunk_count'] == 1
    assert get_video('local-ready-video')['chunk_count'] == 1


def test_ready_local_video_with_stale_counter_can_query_its_indexed_chunks(api_client):
    from videoqa.db.sqlite import insert_chunks

    upsert_video({
        'id': 'video-row-query-local',
        'video_id': 'local-query-video',
        'source_type': 'file_upload',
        'title': 'Local lecture',
        'duration_seconds': 90,
        'chunk_count': 0,
        'status': 'ready',
        'created_at': '2026-10-05T00:00:00+00:00',
        'updated_at': '2026-10-05T00:00:00+00:00',
    })
    insert_chunks([{
        'chunk_id': 'local-query-chunk-1',
        'video_id': 'local-query-video',
        'chunk_index': 0,
        'start_seconds': 31,
        'end_seconds': 45,
        'text': 'The lecture describes reliable request routing.',
        'text_original': 'The lecture describes reliable request routing.',
        'word_count': 6,
        'language': 'en',
    }])

    retrieved = {
        'chunk_id': 'local-query-chunk-1', 'video_id': 'local-query-video',
        'title': 'Local lecture', 'start_seconds': 31.0, 'end_seconds': 45.0,
        'text': 'The lecture describes reliable request routing.', 'similarity': .94,
    }

    class FakeResponse:
        def raise_for_status(self):
            return None

        def iter_lines(self):
            return [b'{"response":"The lecture explains request routing."}']

    with patch('videoqa.api.query.create_embedding', return_value=[[.2, .3]]), \
         patch('videoqa.api.query.search_vectors', return_value=[retrieved]) as search, \
         patch('videoqa.api.query.requests.post', return_value=FakeResponse()):
        response = api_client.post('/api/query', json={
            'question': 'What does the lecture say about routing?',
            'video_id': 'local-query-video',
        })

    assert response.status_code == 200
    search.assert_called_once()
    assert search.call_args.kwargs['video_id'] == 'local-query-video'
    assert 'The lecture explains request routing.' in response.text
    assert '"video_id": "local-query-video"' in response.text
    assert '"start_display": "00:31"' in response.text


@pytest.mark.parametrize(
    ('path', 'requested_method'),
    [('/api/ingest/file', 'POST'), ('/api/health', 'GET')],
)
def test_configured_frontend_cors_preflight_is_allowed(api_client, path, requested_method):
    response = api_client.options(
        path,
        headers={
            'Origin': 'http://localhost:3001',
            'Access-Control-Request-Method': requested_method,
            'Access-Control-Request-Headers': 'content-type',
        },
    )
    assert response.status_code == 200
    assert response.headers['access-control-allow-origin'] == 'http://localhost:3001'
    assert requested_method in response.headers['access-control-allow-methods']
    assert 'content-type' in response.headers['access-control-allow-headers'].lower()


def test_missing_upload_field_returns_fastapi_validation_detail(api_client):
    response = api_client.post('/api/ingest/file')
    assert response.status_code == 422
    issue = response.json()['detail'][0]
    assert issue['loc'] == ['body', 'file']
    assert issue['msg'] == 'Field required'


def test_openapi_has_no_duplicate_operation_ids(api_client):
    schema = api_client.get('/openapi.json').json()
    operation_ids = [
        operation['operationId']
        for path in schema['paths'].values()
        for operation in path.values()
        if isinstance(operation, dict) and 'operationId' in operation
    ]
    assert len(operation_ids) == len(set(operation_ids))


def test_rag_chat_is_rejected_until_ready_chunks_exist(api_client):
    upsert_video({
        'id': 'video-row-processing',
        'video_id': 'processing-video',
        'source_type': 'file_upload',
        'title': 'Still indexing',
        'duration_seconds': 10,
        'status': 'transcribing',
        'created_at': '2026-10-05T00:00:00+00:00',
        'updated_at': '2026-10-05T00:00:00+00:00',
    })
    response = api_client.post('/api/query', json={'question': 'What is covered?', 'video_id': 'processing-video'})
    assert response.status_code == 409
    assert 'indexed' in response.json()['detail']


def test_streamed_query_emits_structured_citations_not_model_authored_links(api_client):
    from videoqa.db.sqlite import insert_chunks

    upsert_video({
        'id': 'video-row-2',
        'video_id': 'dQw4w9WgXcQ',
        'source_type': 'youtube',
        'title': 'Example lesson',
        'duration_seconds': 180,
        'chunk_count': 1,
        'status': 'ready',
        'created_at': '2026-10-05T00:00:00+00:00',
        'updated_at': '2026-10-05T00:00:00+00:00',
    })
    set_chunk_count('dQw4w9WgXcQ', 1)
    insert_chunks([{
        'chunk_id': 'youtube-query-chunk',
        'video_id': 'dQw4w9WgXcQ',
        'chunk_index': 0,
        'start_seconds': 72,
        'end_seconds': 91,
        'text': 'Supporting transcript text.',
        'text_original': 'Supporting transcript text.',
        'word_count': 3,
        'language': 'en',
    }])

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
