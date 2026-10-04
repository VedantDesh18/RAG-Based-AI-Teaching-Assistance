import pytest
from unittest.mock import patch
from videoqa.core.retriever import retrieve
from videoqa.config import config

@patch('videoqa.core.retriever.search_vectors')
@patch('videoqa.core.retriever.create_embedding')
@patch('videoqa.core.retriever.generate_response')
def test_retriever_abstention(mock_generate, mock_embed, mock_search):
    import numpy as np
    
    # Mock embedding for query
    mock_embed.return_value = [np.array([-0.1]*1024)]
    
    # Mock search results with low similarity (below 0.35)
    mock_search.return_value = [
        {"title": "test", "number": "01", "start_seconds": 0, "end_seconds": 1, "text": "dummy", "similarity": 0.1}
    ]
    
    result = retrieve("What is the capital of France?")
    
    assert result["answer"] == "I couldn't find relevant content in this video for your question."
    assert len(result["citations"]) == 0
    mock_generate.assert_not_called()

@patch('videoqa.core.retriever.search_vectors')
@patch('videoqa.core.retriever.create_embedding')
@patch('videoqa.core.retriever.generate_response')
def test_retriever_success(mock_generate, mock_embed, mock_search):
    import numpy as np
    
    mock_embed.return_value = [np.array([0.5]*1024)]
    
    # Mock search results with high similarity
    mock_search.return_value = [
        {"title": "test", "number": "01", "start_seconds": 0, "end_seconds": 1, "text": "dummy text", "similarity": 0.8}
    ]
    
    mock_generate.return_value = "This is a grounded answer."
    
    result = retrieve("Valid query")
    
    assert result["answer"] == "This is a grounded answer."
    assert len(result["citations"]) == 1
    mock_generate.assert_called_once()
