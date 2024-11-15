from typing import List
import numpy as np
from sklearn.metrics.pairwise import cosine_similarity
import pandas as pd

class EmbeddingStore:
    def __init__(self):
        self.embeddings = []
        self.texts = []
        
    async def add_embedding(self, text: str, embedding: List[float]):
        self.embeddings.append(embedding)
        self.texts.append(text)
        
    async def search(self, query_embedding: List[float], top_k: int = 5) -> List[str]:
        if not self.embeddings:
            return []
            
        similarities = cosine_similarity(
            [query_embedding],
            self.embeddings
        )[0]
        
        top_indices = np.argsort(similarities)[-top_k:][::-1]
        return [self.texts[i] for i in top_indices]