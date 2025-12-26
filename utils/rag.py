
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
        Returns top k chunks matching the query.
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
            
        scores = []
        for chunk in self.chunks:
            c_vec = chunk["embedding"]
            c_norm = np.linalg.norm(c_vec)
            
            if c_norm == 0:
                score = 0
            else:
                score = np.dot(q_vec, c_vec) / (q_norm * c_norm)
            
            scores.append((score, chunk))
            
        # Sort by score descending
        scores.sort(key=lambda x: x[0], reverse=True)
        
        # Return just the chunks
        return [s[1] for s in scores[:k]]
        
    def clear(self):
        self.chunks = []
