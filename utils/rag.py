"""
SQLite-backed vector store for RAG.

Provides persistence for document chunks using SQLite, while maintaining
in-memory cache for fast vector similarity search.
"""

import sqlite3
import json
import numpy as np
import logging
import os
from typing import List, Dict, Optional
from utils.llm_handler import get_embedding, MAX_VECTOR_STORE_CHUNKS, MIN_CHUNK_LENGTH

logger = logging.getLogger(__name__)

DB_PATH = "vector_store.db"

class SQLiteVectorStore:
    """
    Persisted vector store using SQLite for storage and in-memory numpy for search.
    
    Attributes:
        db_path: Path to the SQLite database file.
        chunks: In-memory cache of chunks for fast search.
    """
    
    def __init__(self, db_path: str = DB_PATH):
        """Initialize database connection and load cache."""
        self.db_path = db_path
        self._init_db()
        self.chunks: List[Dict] = []
        self._load_cache()
        
    def _init_db(self) -> None:
        """Create tables if they don't exist."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS chunks (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        text TEXT NOT NULL,
                        metadata TEXT,
                        embedding BLOB NOT NULL
                    )
                """)
                conn.commit()
        except Exception as e:
            logger.error(f"Failed to initialize vector DB: {e}")

    def _load_cache(self) -> None:
        """Load all chunks from DB into memory."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT text, metadata, embedding FROM chunks")
                rows = cursor.fetchall()
                
                self.chunks = []
                for text, meta_json, emb_blob in rows:
                    try:
                        embedding = np.frombuffer(emb_blob, dtype=np.float32)
                        metadata = json.loads(meta_json) if meta_json else {}
                        self.chunks.append({
                            "text": text,
                            "metadata": metadata,
                            "embedding": embedding
                        })
                    except Exception as load_err:
                        logger.warning(f"Skipping corrupted chunk: {load_err}")
                
            logger.info(f"Loaded {len(self.chunks)} chunks from persistence.")
        except Exception as e:
            logger.error(f"Failed to load vector cache: {e}")

    def add_chunks(self, chunks: List[str], google_client, metadata_list: List[Dict] = None) -> None:
        """Add chunks to DB and cache."""
        if not metadata_list:
            metadata_list = [{}] * len(chunks)
            
        # OOM/DB Size Protection
        if len(self.chunks) + len(chunks) > MAX_VECTOR_STORE_CHUNKS:
            logger.warning(f"Vector Store capacity reached ({MAX_VECTOR_STORE_CHUNKS}). Truncating.")
            remaining_slots = MAX_VECTOR_STORE_CHUNKS - len(self.chunks)
            if remaining_slots <= 0:
                return
            chunks = chunks[:remaining_slots]
            metadata_list = metadata_list[:remaining_slots]

        new_entries = []
        
        for i, text in enumerate(chunks):
            if len(text) < MIN_CHUNK_LENGTH: 
                continue
                
            emb = get_embedding(text, google_client=google_client) 
            if emb:
                embedding_np = np.array(emb, dtype=np.float32)
                metadata = metadata_list[i]
                
                new_entries.append((
                    text,
                    json.dumps(metadata),
                    embedding_np.tobytes()
                ))
                
                # Update cache
                self.chunks.append({
                    "text": text,
                    "metadata": metadata,
                    "embedding": embedding_np
                })

        # Bulk insert to DB
        if new_entries:
            try:
                with sqlite3.connect(self.db_path) as conn:
                    cursor = conn.cursor()
                    cursor.executemany(
                        "INSERT INTO chunks (text, metadata, embedding) VALUES (?, ?, ?)",
                        new_entries
                    )
                    conn.commit()
            except Exception as e:
                logger.error(f"Failed to persist chunks: {e}")

    def search(self, query: str, google_client, k: int = 5) -> List[Dict]:
        """Search similar chunks using in-memory cache."""
        if not self.chunks:
            return []
            
        query_emb = get_embedding(query, google_client=google_client)
        if not query_emb:
            return []
            
        q_vec = np.array(query_emb, dtype=np.float32)
        q_norm = np.linalg.norm(q_vec)
        
        if q_norm == 0:
            return []
        
        # Vectorized cosine similarity
        embeddings_matrix = np.array([c["embedding"] for c in self.chunks], dtype=np.float32)
        dot_products = np.dot(embeddings_matrix, q_vec)
        norms = np.linalg.norm(embeddings_matrix, axis=1)
        norms[norms == 0] = 1e-10
        scores = dot_products / (norms * q_norm)
        
        top_indices = np.argsort(scores)[::-1][:k]
        
        return [self.chunks[i] for i in top_indices]
        
    def clear(self) -> None:
        """Clear DB and cache."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("DELETE FROM chunks")
                conn.commit()
            self.chunks = []
            if os.path.exists(self.db_path):
                 try:
                     # Optional: vacuum to reclaim space, or remove file
                     pass 
                 except: 
                     pass
        except Exception as e:
            logger.error(f"Failed to clear vector store: {e}")

    def __len__(self) -> int:
        return len(self.chunks)
