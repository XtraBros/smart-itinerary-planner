import pandas as pd
from sentence_transformers import SentenceTransformer
import faiss
import numpy as np
from typing import List

class RAGPlatform:
    def __init__(self, csv_file: str = None, index_file: str = None, embedding_model: str = 'all-MiniLM-L6-v2'):
        self.embedding_model = SentenceTransformer(embedding_model)
        self.data = None
        self.description_index = None
        self.name_index = None
        self.name_embeddings = None
        self.names = []
        self.index_file = index_file
        
        if csv_file:
            self.load_csv(csv_file)
            self.build_index()
        elif index_file:
            raise NotImplementedError("Loading from index file not implemented in this vector-based version.")
        else:
            raise ValueError("Must provide either a csv_file or index_file.")

    def load_csv(self, path: str):
        self.data = pd.read_csv(path)
        if 'description' not in self.data.columns or 'name' not in self.data.columns:
            raise ValueError("CSV must contain 'name' and 'description' columns.")
        self.names = self.data['name'].tolist()

    def build_index(self):
        # Build description index
        descriptions = self.data['description'].tolist()
        desc_embeddings = self.embedding_model.encode(descriptions, convert_to_numpy=True)
        self.description_index = faiss.IndexFlatL2(desc_embeddings.shape[1])
        self.description_index.add(desc_embeddings)

        # Build name index
        self.name_embeddings = self.embedding_model.encode(self.names, convert_to_numpy=True)
        self.name_index = faiss.IndexFlatL2(self.name_embeddings.shape[1])
        self.name_index.add(self.name_embeddings)

        print(f"Built index: {len(desc_embeddings)} descriptions and {len(self.name_embeddings)} names.")

    def query(self, input_text: str, top_k: int = 3) -> List[dict]:
        query_vec = self.embedding_model.encode([input_text], convert_to_numpy=True)
        distances, indices = self.description_index.search(query_vec, top_k)
        results = []
        for idx in indices[0]:
            if idx < len(self.data):
                row = self.data.iloc[idx]
                results.append({'name': row['name'], 'description': row['description']})
        return results

    def match_names_vector(self, input_text: str, top_k: int = 3, distance_threshold: float = 1.0) -> List[str]:
        query_vec = self.embedding_model.encode([input_text], convert_to_numpy=True)
        distances, indices = self.name_index.search(query_vec, top_k)
        matches = []
        for i, dist in zip(indices[0], distances[0]):
            if dist <= distance_threshold:
                matches.append(self.names[i])
        return matches
    
    def filter_by_categories(self, categories: List[str], top_k: int = 5) -> List[dict]:
        if 'category' not in self.data.columns:
            raise ValueError("CSV must contain a 'category' column to use this method.")
        
        # Normalize the category column to lowercase for case-insensitive matching
        data_copy = self.data.copy()
        data_copy['category_lower'] = data_copy['category'].str.lower()
        
        # Lowercase all input categories
        categories = [cat.lower() for cat in categories]
        
        # Filter where category matches any of the given categories
        filtered = data_copy[data_copy['category_lower'].apply(
            lambda x: any(cat in x for cat in categories)
        )]

        results = []
        for _, row in filtered.head(top_k).iterrows():
            results.append({
                'name': row['name'],
                'description': row['description'],
                'category': row['category']
            })
        
        return results

    # Location based searching is dependent on the site's location detection system and the POI data.