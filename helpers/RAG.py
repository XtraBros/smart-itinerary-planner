import uuid
import pandas as pd
import numpy as np
import faiss
from typing import List, Optional
from sentence_transformers import SentenceTransformer
from sklearn.metrics.pairwise import cosine_similarity
from typing import Dict, List, Optional
from sklearn.neighbors import BallTree
import networkx as nx

class RAGUnit:
    def __init__(
        self,
        data_source: dict,
        id: Optional[str] = None,
        description: str = "",
        name: str = ""
    ):
        """
        A retrieval unit that loads a CSV dataset of POIs, builds vector indices,
        and supports semantic + categorical queries.
        """
        self.id = id or str(uuid.uuid4())
        self.source = data_source
        self.description = description
        self.name = name

        self.embedding_model = SentenceTransformer("all-MiniLM-L6-v2")
        self.data = None

        # Embedding stores
        self.name_embeddings = None
        self.description_embeddings = None
        self.tag_embeddings = None

        # FAISS indices
        self.name_index = None
        self.description_index = None
        self.tag_index = None
        self.dining_index = None
        self.dining_data = None

        self.load_data()
        self.build_indices()

    def load_data(self):
        """Load POI data from CSV."""
        path = self.source.get("path")
        if not path:
            raise ValueError("CSV path must be provided in source.")

        try:
            self.data = pd.read_csv(path, encoding="utf-8")
        except UnicodeDecodeError:
            self.data = pd.read_csv(path, encoding="ISO-8859-1")

    def build_indices(self):
        """Build FAISS indices for name, description, and tags."""
        if self.data is None:
            raise ValueError("Data must be loaded before building indices.")

        texts = {
            "name": self.data["name"].astype(str).tolist() if "name" in self.data else [],
            "description": self.data["description"].astype(str).tolist() if "description" in self.data else [],
            "tags": self.data["tags"].astype(str).tolist() if "tags" in self.data else []
        }

        for field, values in texts.items():
            if not values:
                continue
            embeddings = self.embedding_model.encode(values, convert_to_numpy=True)
            dim = embeddings.shape[1]
            index = faiss.IndexFlatL2(dim)
            index.add(embeddings.astype("float32"))
            setattr(self, f"{field}_embeddings", embeddings)
            setattr(self, f"{field}_index", index)

        # Optional dining index
        if "category" in self.data.columns:
            dining_mask = self.data["category"].str.lower() == "dining"
            dining_data = self.data[dining_mask].reset_index(drop=True)
            if not dining_data.empty:
                dining_descs = dining_data["description"].astype(str).tolist()
                dining_embeddings = self.embedding_model.encode(dining_descs, convert_to_numpy=True)
                dim = dining_embeddings.shape[1]
                self.dining_index = faiss.IndexFlatL2(dim)
                self.dining_index.add(dining_embeddings.astype("float32"))
                self.dining_data = dining_data

    def query_by(self, field: str, input_text: str, top_k: int = 5) -> List[dict]:
        """Query POIs by semantic similarity on the given field (name, description, tags)."""
        index = getattr(self, f"{field}_index", None)
        embeddings = getattr(self, f"{field}_embeddings", None)
        if index is None or embeddings is None:
            return []

        query_vec = self.embedding_model.encode([input_text], convert_to_numpy=True)
        query_vec = np.atleast_2d(query_vec).astype("float32")
        distances, indices = index.search(query_vec, top_k)

        results = []
        for rank, idx in enumerate(indices[0]):
            if idx < len(self.data):
                row = self.data.iloc[idx]
                results.append({
                    "name": row.get("name", ""),
                    "description": row.get("description", ""),
                    "longitude": row.get("longitude"),
                    "latitude": row.get("latitude"),
                    "category": row.get("category", ""),
                    "operating_hours": row.get("operating_hours", ""),
                    "tags": row.get("tags", ""),})
        return results

    def filter_by_categories(self, categories: List[str]) -> List[dict]:
        """Return all POIs matching any of the given categories."""
        if self.data is None or "category" not in self.data.columns:
            return []

        mask = self.data["category"].str.lower().isin([c.lower() for c in categories])
        return self.data[mask].to_dict(orient="records")

    def get_data(self) -> pd.DataFrame:
        """Return the underlying dataframe."""
        return self.data
    
    def get_location_data(self) -> pd.DataFrame:
        """Return a DataFrame with (name, longitude, latitude) for map use."""
        if self.data is not None:
            required = {"name", "longitude", "latitude"}
            if required.issubset(self.data.columns):
                return self.data[list(required)].dropna()
        return pd.DataFrame(columns=["name", "longitude", "latitude"])


class RAGPlatform:
    def __init__(self, rag_units: List[RAGUnit] = None):
        self.units: Dict[str, RAGUnit] = {unit.id: unit for unit in rag_units or []}

    def add_unit(self, unit: RAGUnit):
        self.units[unit.id] = unit

    def query_by_name(self, query_text: str, top_k: int = 5) -> List[dict]:
        return self._aggregate_query("name", query_text, top_k)

    def query_by_description(self, query_text: str, top_k: int = 5) -> List[dict]:
        return self._aggregate_query("description", query_text, top_k)

    def query_by_tags(self, tags: List[str], top_k: int = 5) -> List[dict]:
        query_text = ", ".join(tags)
        return self._aggregate_query("tags", query_text, top_k)

    def _aggregate_query(self, field: str, query_text: str, top_k: int) -> List[dict]:
        results = []
        for unit in self.units.values():
            try:
                unit_results = unit.query_by(field, query_text, top_k)
                for r in unit_results:
                    r["source"] = unit.name
                    results.append(r)
            except Exception as e:
                print(f"[{unit.id}] Error during {field} query: {e}")
        return sorted(results, key=lambda x: x.get("similarity", 0), reverse=True)[:top_k]
    
    def hybrid_query(self, query_text: str, top_k: int = 5, alpha: float = 0.5) -> List[dict]:
        """
        Hybrid retrieval between tags and descriptions using weighted score fusion.
        alpha = weight for description score (0-1).
        """
        desc_results = self.query_by("description", query_text, top_k * 2)
        tag_results = self.query_by("tags", query_text, top_k * 2)

        # Build lookup tables for merging
        merged = {}
        for r in desc_results:
            merged[r["name"]] = {
                **r,
                "desc_score": 1.0 / (1.0 + r["similarity"]),  # invert distance to similarity
                "tag_score": 0.0
            }

        for r in tag_results:
            if r["name"] in merged:
                merged[r["name"]]["tag_score"] = 1.0 / (1.0 + r["similarity"])
            else:
                merged[r["name"]] = {
                    **r,
                    "desc_score": 0.0,
                    "tag_score": 1.0 / (1.0 + r["similarity"])
                }

        # Hybrid score = α * desc_score + (1-α) * tag_score
        for v in merged.values():
            v["hybrid_score"] = alpha * v["desc_score"] + (1 - alpha) * v["tag_score"]

        # Sort and return top-k
        results = sorted(merged.values(), key=lambda x: x["hybrid_score"], reverse=True)
        return results[:top_k]
    
    def build_balltree(self):
        """Build BallTree from all units' POI data and store internally."""
        all_pois = []
        for unit in self.units.values():
            try:
                df = unit.get_location_data()
                if not df.empty:
                    all_pois.append(df)
            except Exception as e:
                print(f"[{unit.id}] Failed to fetch location data: {e}")

        if not all_pois:
            raise ValueError("No POIs with valid coordinates found.")

        combined_df = pd.concat(all_pois, ignore_index=True)
        coords_rad = np.radians(combined_df[['latitude', 'longitude']].values)
        tree = BallTree(coords_rad, metric='haversine')

        self.balltree_df = combined_df
        self.balltree = tree
        return tree, combined_df

    def update_balltree(self, poi_df):
        """Rebuild BallTree from a given POI dataframe."""
        coordinates_rad = np.radians(poi_df[['latitude', 'longitude']].values)
        ball_tree = BallTree(coordinates_rad, metric='haversine')
        self.balltree_df = poi_df
        self.balltree = ball_tree
        return ball_tree

    def build_graph(self, k=5):
        """Build a k-NN graph from the current BallTree + POIs."""
        if self.balltree is None or self.balltree_df is None:
            raise ValueError("BallTree not initialized. Run build_balltree() first.")

        earth_radius = 6371000  # meters
        coords_rad = np.radians(self.balltree_df[['latitude', 'longitude']].values)
        names = self.balltree_df['name'].tolist()

        G = nx.Graph()
        for i, name in enumerate(names):
            row = self.balltree_df.iloc[i]
            G.add_node(name, pos=(row['longitude'], row['latitude']))

            # Query k nearest neighbors (excluding self)
            dist, ind = self.balltree.query([coords_rad[i]], k=k+1)
            for j, d in zip(ind[0][1:], dist[0][1:]):  # skip self
                neighbor_name = names[j]
                distance_m = d * earth_radius
                G.add_edge(name, neighbor_name, weight=distance_m)

        self.graph = G
        return G

    def build_distance_matrix(self, place_names):
        """Compute distance matrix between selected POIs."""
        if self.balltree is None or self.balltree_df is None:
            raise ValueError("BallTree not initialized. Run build_balltree() first.")

        name_to_index = {name: idx for idx, name in enumerate(self.balltree_df['name'])}
        indices = [name_to_index[name] for name in place_names]
        coords_subset = np.radians(self.balltree_df.iloc[indices][['latitude', 'longitude']].to_numpy())

        earth_radius = 6371000  # meters
        dist_matrix = np.zeros((len(indices), len(indices)))

        for i, coord in enumerate(coords_subset):
            dists, _ = self.balltree.query([coord], k=len(coords_subset))
            dist_matrix[i] = dists[0][:len(indices)] * earth_radius

        return pd.DataFrame(dist_matrix, index=place_names, columns=place_names)

    def solve_route(self, place_names, tsp_solver):
        """Solve route between given POIs using TSP solver and BallTree distances."""
        dist_df = self.build_distance_matrix(place_names)
        permutation = tsp_solver(dist_df)
        return permutation
    
    def spatial_query(self, lat: float, lon: float, k: int = 5, radius_km: float = None):
        """
        Query the BallTree for nearest neighbors by location.
        Args:
            lat (float): latitude in degrees
            lon (float): longitude in degrees
            k (int): number of neighbors to return
            radius_km (float, optional): filter results within this radius in km

        Returns:
            List[dict]: POIs with distance (km)
        """
        if not hasattr(self, "balltree"):
            raise ValueError("BallTree not built. Call build_balltree() first.")

        query_point = np.radians([[lat, lon]])
        distances, indices = self.balltree.query(query_point, k=k)

        results = []
        for dist, idx in zip(distances[0], indices[0]):
            row = self.balltree_df.iloc[idx].to_dict()
            row["distance_km"] = dist * 6371  # haversine distance in km
            if radius_km is None or row["distance_km"] <= radius_km:
                results.append(row)

        return results
    
    def list_units(self) -> List[dict]:
        """List all tracked RAGUnits with metadata."""
        return [
            {
                "id": unit.id,
                "name": unit.name,
                "description": unit.description,
                "source_type": unit.source.get("type", "unknown")
            }
            for unit in self.units.values()
        ]
    
    def get_coordinates(self, poi_name):
        """
        Return (longitude, latitude) tuple for the given POI name.
        
        Args:
            poi_name (str): The name of the POI to look up.
        
        Returns:
            tuple: (longitude, latitude) if found, else None.
        """
        if self.balltree_df is None:
            raise ValueError("BallTree dataframe not initialized. Run build_balltree() first.")
        
        row = self.balltree_df.loc[self.balltree_df['name'] == poi_name]
        if row.empty:
            return None  # or raise an error if you prefer
        
        lon, lat = row.iloc[0]['longitude'], row.iloc[0]['latitude']
        return (lon, lat)
    
    def get_poi_details(self, poi_names):
        """
        Return details (name, longitude, latitude, description) for a list of POI names.

        Args:
            poi_names (list[str]): List of POI names.

        Returns:
            list[dict]: Each dict contains {name, longitude, latitude, description}.
        """
        if self.balltree_df is None:
            raise ValueError("BallTree dataframe not initialized. Run build_balltree() first.")

        details = []
        for name in poi_names:
            row = self.balltree_df.loc[self.balltree_df['name'] == name]
            if row.empty:
                continue  # skip missing names (or raise if strict required)

            r = row.iloc[0]
            details.append({
                "name": r["name"],
                "longitude": r["longitude"],
                "latitude": r["latitude"],
                "description": r.get("description", "")
            })

        return details