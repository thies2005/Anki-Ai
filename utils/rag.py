
import numpy as np
import pandas as pd
from utils.llm_handler import get_embedding

class SimpleVectorStore:
    def __init__(self):
        self.chunks = [] # List of {"text": str, "metadata": dict, "embedding": np.array}
    
    def add_chunks(self, chunks: list[str], google_client, metadata_list: list[dict] = None):
        """
        Adds text chunks to the store. 
        Note: This processes embeddings serially and might be slow for very large docs.
        """
        if not metadata_list:
            metadata_list = [{}] * len(chunks)
            
        # OOM Protection: Limit total chunks
        if len(self.chunks) + len(chunks) > 5000:
            print("Warning: Vector Store capacity reached (5000 chunks). Truncating.")
            remaining_slots = 5000 - len(self.chunks)
            if remaining_slots <= 0: return
            chunks = chunks[:remaining_slots]
            metadata_list = metadata_list[:remaining_slots]

        for i, text in enumerate(chunks):
            # optimization: skip very short chunks
            if len(text) < 50: continue
            
            emb = get_embedding(text, google_client=google_client) 
            if emb:
                self.chunks.append({
                    "text": text,
                    "metadata": metadata_list[i],
                    "embedding": np.array(emb, dtype=np.float32)
                })
                
    def search(self, query: str, google_client, k: int = 5) -> list[dict]:
        """
        Returns top k chunks matching the query using vectorized cosine similarity.
        """
        if not self.chunks:
            return []
            
        query_emb = get_embedding(query, google_client=google_client)
        if not query_emb:
            return []
            
        q_vec = np.array(query_emb, dtype=np.float32)
        q_norm = np.linalg.norm(q_vec)
        
        if q_norm == 0:
            return []
        
        # Vectorized: Build matrix of all embeddings
        embeddings_matrix = np.array([c["embedding"] for c in self.chunks], dtype=np.float32)
        
        # Compute all dot products at once
        dot_products = np.dot(embeddings_matrix, q_vec)
        
        # Compute norms for all chunk vectors
        norms = np.linalg.norm(embeddings_matrix, axis=1)
        
        # Avoid division by zero
        norms[norms == 0] = 1e-10
        
        # Cosine similarity scores
        scores = dot_products / (norms * q_norm)
        
        # Get top k indices
        top_indices = np.argsort(scores)[::-1][:k]
        
        return [self.chunks[i] for i in top_indices]
        
    def clear(self):
        self.chunks = []
