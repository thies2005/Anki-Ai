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
        conn = None
        try:
            conn = sqlite3.connect(self.db_path)
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
                except (ValueError, json.JSONDecodeError) as load_err:
                    logger.warning(f"Skipping corrupted chunk: {load_err}")

            logger.info(f"Loaded {len(self.chunks)} chunks from persistence.")
        except sqlite3.Error as e:
            logger.error(f"Database error loading vector cache: {e}")
        except Exception as e:
            logger.error(f"Failed to load vector cache: {e}")
        finally:
            if conn:
                conn.close()

    def add_chunks(self, chunks: List[str], google_client, zai_client=None, metadata_list: List[Dict] = None) -> None:
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
        valid_indices = []
        
        # Identify valid chunks first
        for i, text in enumerate(chunks):
            if len(text) >= MIN_CHUNK_LENGTH:
                valid_indices.append(i)

        # Process in batches
        BATCH_SIZE = 100
        for i in range(0, len(valid_indices), BATCH_SIZE):
            batch_indices = valid_indices[i : i + BATCH_SIZE]
            batch_texts = [chunks[idx] for idx in batch_indices]

            # Batch embedding call
            embeddings = get_embedding(batch_texts, google_client=google_client, zai_client=zai_client)

            # Validate response
            if not embeddings or len(embeddings) != len(batch_texts):
                logger.warning(f"Batch embedding failed or mismatch (Got {len(embeddings) if embeddings else 0}, Expected {len(batch_texts)}). Processing individually.")
                # Fallback to individual processing
                embeddings = []
                for text in batch_texts:
                    embeddings.append(get_embedding(text, google_client=google_client, zai_client=zai_client))

            for j, emb in enumerate(embeddings):
                if emb:
                    original_idx = batch_indices[j]
                    text = chunks[original_idx]
                    metadata = metadata_list[original_idx]

                    embedding_np = np.array(emb, dtype=np.float32)

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
            conn = None
            try:
                conn = sqlite3.connect(self.db_path)
                cursor = conn.cursor()
                cursor.executemany(
                    "INSERT INTO chunks (text, metadata, embedding) VALUES (?, ?, ?)",
                    new_entries
                )
                conn.commit()
            except sqlite3.Error as e:
                logger.error(f"Database error persisting chunks: {e}")
            except Exception as e:
                logger.error(f"Failed to persist chunks: {e}")
            finally:
                if conn:
                    conn.close()

    def search(self, query: str, google_client, zai_client=None, k: int = 5) -> List[Dict]:
        """Search similar chunks using in-memory cache."""
        if not self.chunks:
            return []
            
        query_emb = get_embedding(query, google_client=google_client, zai_client=zai_client)
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
        conn = None
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute("DELETE FROM chunks")
            conn.commit()
            self.chunks = []
            if os.path.exists(self.db_path):
                try:
                    # Vacuum to reclaim space
                    conn.execute("VACUUM")
                except sqlite3.Error:
                    pass
        except sqlite3.Error as e:
            logger.error(f"Database error clearing vector store: {e}")
        except Exception as e:
            logger.error(f"Failed to clear vector store: {e}")
        finally:
            if conn:
                conn.close()

    def __len__(self) -> int:
        return len(self.chunks)
