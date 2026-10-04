import os
import json
import pytest
from videoqa.core.chunker import merge_chunks
from videoqa.config import config

def test_merge_chunks(tmp_path):
    # Setup mock input data
    input_dir = tmp_path / "jsons"
    output_dir = tmp_path / "newjsons"
    input_dir.mkdir()
    
    # 7 segments
    mock_segments = [
        {"number": "01", "title": "test", "start": 0.0, "end": 2.0, "text": "Hello"},
        {"number": "01", "title": "test", "start": 2.0, "end": 4.0, "text": "World"},
        {"number": "01", "title": "test", "start": 4.0, "end": 6.0, "text": "This"},
        {"number": "01", "title": "test", "start": 6.0, "end": 8.0, "text": "is"},
        {"number": "01", "title": "test", "start": 8.0, "end": 10.0, "text": "a"},
        {"number": "01", "title": "test", "start": 10.0, "end": 12.0, "text": "test"},
        {"number": "01", "title": "test", "start": 12.0, "end": 14.0, "text": "chunk"},
    ]
    
    with open(input_dir / "test_video.json", "w", encoding="utf-8") as f:
        json.dump({"chunks": mock_segments, "text": "Hello World This is a test chunk"}, f)
        
    merge_chunks(str(input_dir), str(output_dir))
    
    assert (output_dir / "test_video.json").exists()
    
    with open(output_dir / "test_video.json", "r", encoding="utf-8") as f:
        data = json.load(f)
    
    # Config is 5 segments per chunk by default
    assert len(data["chunks"]) == 2
    
    chunk1 = data["chunks"][0]
    assert chunk1["start"] == 0.0
    assert chunk1["end"] == 10.0
    assert chunk1["text"] == "Hello World This is a"
    assert chunk1["chunk_index"] == 0
    
    chunk2 = data["chunks"][1]
    assert chunk2["start"] == 10.0
    assert chunk2["end"] == 14.0
    assert chunk2["text"] == "test chunk"
    assert chunk2["chunk_index"] == 1
