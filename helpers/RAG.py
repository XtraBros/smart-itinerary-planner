import pandas as pd
from sentence_transformers import SentenceTransformer
import uuid
from typing import List, Optional, Dict
import pandas as pd
from sentence_transformers import SentenceTransformer
from sqlalchemy import create_engine
from pymongo import MongoClient
import numpy as np
import faiss

'''
RAGUnit: One unit of RAG platform
Uses a SINGLE data source for retrieval.
Supports: CSV, SQL, MongoDB, JSON, and CMS (stub).
From a SQL database:
source = {
    "type": "sql",
    "url": "sqlite:///my_database.db",  # or "postgresql://user:pass@host:port/db"
    "query": "SELECT name, description FROM pois"
}
From MongoDB:
source = {
    "type": "mongo",
    "uri": "mongodb://localhost:27017",
    "db": "mydb",
    "collection": "pois"
}
From a CSV
source = {
    "type": "csv",
    "path": "uploaded.csv"
}
init: 
rag = RAGPlatform(data_source=source)
'''
class RAGUnit:
    def __init__(
        self,
        embedding_model: str = 'all-MiniLM-L6-v2',
        data_source: Optional[dict] = None,
        id: Optional[str] = None,
        description: str = "",
        name: str = ""
    ):
        
        self.id = id or str(uuid.uuid4())  # Auto-generate UUID if not provided
        self.description = description
        self.embedding_model = SentenceTransformer(embedding_model)
        self.data = None
        self.description_index = None
        self.name_index = None
        self.name_embeddings = None
        self.names = []
        self.source = data_source
        self.description_embeddings = None
        self.name = name

        if data_source:
            self.load_data(data_source)
            self.build_index()
        else:
            raise ValueError("A valid data_source must be provided")

    def load_data(self, source: dict):
        """
        Dynamically load data based on source type. Supported types:
        - csv: path to CSV file
        - sql: dict with 'url' and 'query'
        - mongo: dict with 'uri', 'db', 'collection'
        - json: path to JSON file
        - cms: stub for future API-based loading
        """
        source_type = source.get("type")
        
        if source_type == "csv":
            self.data = pd.read_csv(source.get("path"))
        elif source_type == "excel":
            self.data = pd.read_excel(source.get("path"))
        elif source_type == "sql":
            self.data = self.load_sql(source.get("url"), source.get("query"))
        elif source_type == "mongo":
            self.data = self.load_mongodb(source.get("uri"), source.get("db"), source.get("collection"))
        elif source_type == "json":
            self.data = pd.read_json(source.get("path"))
        elif source_type == "cms":
            self.data = self.load_cms(source.get("api_url"), source.get("auth"))
        else:
            raise ValueError(f"Unsupported source type: {source_type}")

    def load_sql(self, url: str, query: str) -> pd.DataFrame:
        engine = create_engine(url)
        return pd.read_sql_query(query, engine)

    def load_mongodb(self, uri: str, db_name: str, collection_name: str) -> pd.DataFrame:
        client = MongoClient(uri)
        collection = client[db_name][collection_name]
        docs = list(collection.find())
        return pd.DataFrame(docs)

    def load_cms(self, api_url: str, auth: Optional[dict] = None) -> pd.DataFrame:
        # Stub for API-based CMS ingestion
        # Example auth: {"token": "abc"} or {"user": "x", "pass": "y"}
        raise NotImplementedError("CMS data loading not implemented yet")

    def build_index(self):
        if self.data is None:
            raise ValueError("Data must be loaded before building the index.")

        if 'description' not in self.data.columns or 'name' not in self.data.columns:
            raise ValueError("Data must include 'name' and 'description' columns.")

        self.names = self.data["name"].tolist()
        name_texts = self.data["name"].astype(str).tolist()
        desc_texts = self.data["description"].astype(str).tolist()

        self.name_embeddings = self.embedding_model.encode(name_texts, convert_to_numpy=True)
        self.description_embeddings = self.embedding_model.encode(desc_texts, convert_to_numpy=True)

        # Build FAISS indices
        dim = self.description_embeddings.shape[1]
        self.description_index = faiss.IndexFlatL2(dim)
        self.description_index.add(np.array(self.description_embeddings, dtype='float32'))

        self.name_index = faiss.IndexFlatL2(dim)
        self.name_index.add(np.array(self.name_embeddings, dtype='float32'))


    def query(self, input_text: str, top_k: int = 3) -> List[dict]:
        if self.description_index is not None:
            # Use vector search
            query_vec = self.embedding_model.encode([input_text], convert_to_numpy=True).astype("float32")
            distances, indices = self.description_index.search(query_vec, top_k)
            results = []
            for idx in indices[0]:
                if idx < len(self.data):
                    row = self.data.iloc[idx]
                    results.append({'name': row['name'], 'description': row['description']})
            return results
        else:
            # Fallback to text search
            mask = self.data["description"].str.contains(input_text, case=False, na=False)
            filtered = self.data[mask].head(top_k)
            return [
                {"name": row["name"], "description": row["description"]}
                for _, row in filtered.iterrows()
            ]


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

class RAGPlatform:
    def __init__(self, rag_units: List[RAGUnit] = None):
        self.units: Dict[str, RAGUnit] = {}
        if rag_units:
            for unit in rag_units:
                self.units[unit.id] = unit

    def add_unit(self, unit: RAGUnit):
        """Add a new RAGUnit instance."""
        self.units[unit.id] = unit

    def remove_unit_by_id(self, unit_id: str):
        """Remove an existing RAGUnit by its ID."""
        if unit_id in self.units:
            del self.units[unit_id]

    def list_units(self) -> List[dict]:
        """List all tracked RAGUnits with metadata."""
        return [
            {
                "id": unit.id,
                "description": unit.description,
                "source_type": unit.source.get("type", "unknown")
            }
            for unit in self.units.values()
        ]

    def query(self, query_text: str) -> List[dict]:
        """Send query to all units and aggregate non-empty results."""
        results = []
        for unit in self.units.values():
            try:
                result = unit.query(query_text)
                if result:
                    results.extend(result)
            except Exception as e:
                print(f"[{unit.id}] Error during query: {e}")
        return results
    
def location_lookup(user_query: str, rag_platform: RAGPlatform, top_k: int = 3) -> List[dict]:
    """
    Finds the most relevant POIs mentioned in the user query based on name similarity.
    
    Parameters:
        user_query (str): User's location-related question
        rag_platform (RAGPlatform): The central platform containing all RAG units
        top_k (int): Number of matches to return
    
    Returns:
        List[dict]: List of matched POIs with name, description, and optional location data
    """
    matched_pois = []

    for unit in rag_platform.units.values():
        try:
            matched_names = unit.match_names_vector(user_query, top_k=top_k)
            if matched_names:
                for name in matched_names:
                    poi_row = unit.data[unit.data['name'] == name].iloc[0]  # assume exact match
                    result = {
                        'name': poi_row['name'],
                        'description': poi_row['description']
                    }
                    # Optionally include coordinates if available
                    if 'longitude' in poi_row and 'latitude' in poi_row:
                        result['longitude'] = poi_row['longitude']
                        result['latitude'] = poi_row['latitude']
                    matched_pois.append(result)
        except Exception as e:
            print(f"[{unit.name}] Location lookup error: {e}")

    return matched_pois
