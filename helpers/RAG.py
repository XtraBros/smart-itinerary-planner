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
import requests
import sqlalchemy
import pymongo

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
            try:
                self.data = pd.read_csv(source.get("path"), encoding="utf-8")
            except UnicodeDecodeError:
                self.data = pd.read_csv(source.get("path"), encoding="ISO-8859-1")
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
        print(f"{self.name} Name index size:", self.name_index.ntotal)
        print(f"{self.name} Name list size:", len(self.names))
        print(f"{self.name} Description index size:", self.description_index.ntotal)

    def query(self, input_text: str, top_k: int = 3) -> List[dict]:
        if self.description_index is not None:
            # Use vector search
            query_vec = self.embedding_model.encode(input_text, convert_to_numpy=True)
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
        
    def get_data(self):
        if self.data is not None:
            return self.data

        source_type = self.data_source["type"]

        if source_type == "csv":
            df = pd.read_csv(self.data_source["path"])

        elif source_type == "json":
            df = pd.read_json(self.data_source["path"])

        elif source_type == "excel":
            df = pd.read_excel(self.data_source["path"])

        elif source_type == "mongo":
            uri = self.data_source["uri"]
            db_name = self.data_source["db"]
            collection = self.data_source["collection"]

            client = pymongo.MongoClient(uri)
            db = client[db_name]
            collection = db[collection]
            docs = list(collection.find({}, {"_id": 0}))
            df = pd.DataFrame(docs)

        elif source_type == "sql":
            user = self.data_source.get("user")
            password = self.data_source.get("password")
            host = self.data_source.get("host")
            port = self.data_source.get("port", 3306)
            database = self.data_source["database"]
            query = self.data_source["query"]

            # Compose SQLAlchemy URI
            if user and password:
                uri = f"mysql+pymysql://{user}:{password}@{host}:{port}/{database}"
            else:
                uri = f"mysql+pymysql://{host}:{port}/{database}"

            engine = sqlalchemy.create_engine(uri)
            df = pd.read_sql(query, con=engine)

        elif source_type == "cms":
            api_url = self.data_source["api_url"]
            headers = {}
            if self.data_source.get("auth"):
                token = self.data_source["auth"].get("token")
                if token:
                    headers["Authorization"] = f"Bearer {token}"

            response = requests.get(api_url, headers=headers)
            if response.status_code != 200:
                raise Exception(f"Failed to fetch CMS data: {response.text}")
            data = response.json()

            # Handle cases where CMS returns a list or nested structure
            if isinstance(data, dict) and "results" in data:
                data = data["results"]
            df = pd.DataFrame(data)

        else:
            raise ValueError(f"Unsupported data source type: {source_type}")

        self.data = df
        return df
    
    def match_names_vector(
        self, input_text: str, top_k: int = 3, distance_threshold: float = 0.4, is_facility: bool = False
    ) -> List[str]:
        if self.name_index is None or len(self.names) == 0:
            return []

        # Keywords you want to filter out unless is_facility is True
        unwanted_keywords = ["elevator", "toilet", "restroom", "escalator", "parking"]
        if isinstance(input_text, str):
            input_list = [input_text]
        elif isinstance(input_text, list) and all(isinstance(x, str) for x in input_text):
            input_list = input_text
        else:
            raise ValueError("input_text must be a string or list of strings.")
        if not input_list:
            print("Warning: Empty input passed to embedding model.")
            return []
        # Run vector search
        query_vec = self.embedding_model.encode(input_list, convert_to_numpy=True)
        distances, indices = self.name_index.search(query_vec, top_k)

        matches = []
        for i, dist in zip(indices[0], distances[0]):
            if i == -1 or i >= len(self.names):
                continue
            if dist <= distance_threshold:
                name = str(self.names[i])
                if is_facility:
                    matches.append(name)
                elif not any(kw in name.lower() for kw in unwanted_keywords):
                    matches.append(name)
        print(matches)
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
    
    def get_location_data(self) -> pd.DataFrame:
        """
        Returns a DataFrame with 'name', 'longitude', and 'latitude' columns.
        Should return an empty DataFrame if not applicable.
        """
        if hasattr(self, "data") and isinstance(self.data, pd.DataFrame):
            required = {'name', 'longitude', 'latitude'}
            if required.issubset(self.data.columns):
                return self.data[list(required)].dropna()
        # fallback or raise warning if not available
        return pd.DataFrame(columns=['name', 'longitude', 'latitude'])

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
    
    def search_by_field(self, field_name, field_value):
        """
        Search all RAG units for entries where field_name equals field_value.
        Returns a list of dicts containing matched entries.
        """
        results = []

        for unit in self.units.values():
            try:
                data = unit.get_data()

                # Ensure field exists
                if field_name not in data.columns:
                    continue

                # Filter by field using pandas
                filtered = data[data[field_name] == field_value]

                # Convert to list of dicts
                matches = filtered.to_dict(orient='records')
                results.extend(matches)

            except Exception as e:
                print(f"Error during filtering: {e}")

        return results
    
    def location_lookup(self, name_list: List[str], top_k: int = 1) -> List[dict]:
        """
        Finds the most relevant POIs based on a list of names.

        Parameters:
            name_list (List[str]): List of POI names to look up.
            top_k (int): Number of top matches to return per name and unit.

        Returns:
            List[dict]: List of matched POIs with name, description, and optional location data.
        """
        matched_pois = []
        seen_names = set()  # To avoid duplicate POIs

        for name_query in name_list:
            for unit in self.units.values():
                try:
                    matched_names = unit.match_names_vector(name_query, top_k=top_k)
                    if matched_names:
                        for name in matched_names:
                            if name in seen_names:
                                continue
                            poi_row = unit.data[unit.data['name'] == name].iloc[0]
                            result = {
                                'name': poi_row['name'],
                                'description': poi_row['description']
                            }
                            if 'longitude' in poi_row and 'latitude' in poi_row:
                                result['longitude'] = poi_row['longitude']
                                result['latitude'] = poi_row['latitude']
                            matched_pois.append(result)
                            seen_names.add(name)
                except Exception as e:
                    print(f"[{unit.name}] Location lookup error: {e}")

        return matched_pois
    
    def get_all_pois_as_dataframe(self):
        all_dfs = []
        for unit in self.units.values():
            df = unit.get_data()
            all_dfs.append(df)
        if all_dfs:
            return pd.concat(all_dfs, ignore_index=True)
        else:
            return pd.DataFrame()


##################################### Other Functions #####################################

