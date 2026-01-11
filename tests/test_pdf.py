"""
Tests for PDF processing utilities.
"""
import pytest
from utils.pdf_processor import clean_text, recursive_character_text_splitter

def test_clean_text():
    raw = "Hello   World. \n This is \t a test."
    cleaned = clean_text(raw)
    assert cleaned == "Hello World. This is a test."

def test_text_splitter_basic():
    text = "A" * 100
    chunks = recursive_character_text_splitter(text, chunk_size=30, overlap=0)
    assert len(chunks) == 4
    assert len(chunks[0]) == 30
    assert len(chunks[3]) == 10

def test_text_splitter_overlap():
    text = "0123456789"
    # Chunk 5, overlap 2
    # 01234
    #    34567
    #       6789
    chunks = recursive_character_text_splitter(text, chunk_size=5, overlap=2)
    assert len(chunks) >= 2
    assert "34" in chunks[1]
