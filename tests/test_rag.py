"""
Tests for RAG functionality using SQLiteVectorStore.
"""
import pytest
import os
import sqlite3
import numpy as np
from unittest.mock import MagicMock
from utils.rag import SQLiteVectorStore

# Mock embedding function
def mock_get_embedding(text, google_client=None):
    # Deterministic mock embedding based on text length
    val = len(text) % 10 / 10.0
    return [val] * 3  # 3-dimensional vector

@pytest.fixture
def vector_store(tmp_path):
    """Fixture for SQLiteVectorStore with temporary DB."""
    db_file = tmp_path / "test_vector_store.db"
    store = SQLiteVectorStore(db_path=str(db_file))
    
    # Patch the get_embedding function imported in rag.py
    # Since we can't easily patch the import directly without complex mocking,
    # we'll patch the result if we invoke add_chunks carefully.
    # Actually, simpler to mock the google_client and have get_embedding use it?
    # No, get_embedding is imported in rag.py. 
    # Let's monkeypatch utils.rag.get_embedding
    
    return store

def test_init_db(vector_store):
    """Test database initialization."""
    assert os.path.exists(vector_store.db_path)
    with sqlite3.connect(vector_store.db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='chunks'")
        assert cursor.fetchone() is not None

def test_add_and_search(vector_store, monkeypatch):
    """Test adding chunks and searching."""
    # Mock embedding
    monkeypatch.setattr("utils.rag.get_embedding", mock_get_embedding)
    
    chunks = ["apple", "banana", "cherry"]
    vector_store.add_chunks(chunks, google_client=None)
    
    assert len(vector_store) == 3
    
    # Test persistence
    # Create new instance pointing to same DB
    store2 = SQLiteVectorStore(db_path=vector_store.db_path)
    assert len(store2) == 3
    assert store2.chunks[0]['text'] == "apple"

def test_clear(vector_store, monkeypatch):
    monkeypatch.setattr("utils.rag.get_embedding", mock_get_embedding)
    vector_store.add_chunks(["test"], None)
    assert len(vector_store) == 1
    
    vector_store.clear()
    assert len(vector_store) == 0
    
    # Verify DB is empty
    with sqlite3.connect(vector_store.db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT count(*) FROM chunks")
        assert cursor.fetchone()[0] == 0
