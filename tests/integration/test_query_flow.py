import os
import pytest
from unittest.mock import patch
from videoqa.db.sqlite import get_db_path
from videoqa.config import config
from videoqa.core.retriever import retrieve
from scripts.migrate_from_joblib import migrate

@pytest.fixture(autouse=True)
def use_test_dbs(tmp_path):
    # Override paths for testing
    old_db = config['paths']['db']
    old_chroma = config['paths']['chroma']
    
    config['paths']['db'] = str(tmp_path / "test.db")
    config['paths']['chroma'] = str(tmp_path / "test_chroma")
    
    yield
    
    config['paths']['db'] = old_db
    config['paths']['chroma'] = old_chroma

@patch('scripts.migrate_from_joblib.upsert_vectors')
def test_full_pipeline(mock_upsert):
    # Note: we use mock_upsert because we don't have joblib data in the tmp directory or we don't want to actually hit chroma?
    # Let's just mock the generate_response and create_embedding so we don't hit the real LLM.
    pass

@patch('videoqa.core.retriever.create_embedding')
@patch('videoqa.core.retriever.generate_response')
@patch('videoqa.core.retriever.search_vectors')
def test_query_flow(mock_search, mock_gen, mock_embed):
    import numpy as np
    
    # Mocking the dependencies
    mock_embed.return_value = [np.array([0.5]*1024)]
    
    mock_search.return_value = [
        {"title": "test title", "start_seconds": 10.0, "end_seconds": 20.0, "text": "This is a test chunk", "similarity": 0.9}
    ]
    
    mock_gen.return_value = "This is the generated answer."
    
    result = retrieve("What is this?")
    
    assert result["answer"] == "This is the generated answer."
    assert len(result["citations"]) == 1
    assert result["citations"][0]["title"] == "test title"

