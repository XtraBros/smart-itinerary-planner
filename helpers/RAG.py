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
from helpers.text_processing import normalize_name
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
        self.combined_embeddings = None

        # FAISS indices
        self.dining_index = None
        self.dining_data = None
        self.combined_index = None

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
        self.name_to_idx = {
            normalize_name(name): i
            for i, name in enumerate(self.data["name"].astype(str).tolist())
        }
        # Combined embeddings for all fields + metadata ---
        combined_texts = []
        for _, row in self.data.iterrows():
            parts = [
                str(row.get("name", "")),
                str(row.get("description", "")),
                str(row.get("tags", "")),
                str(row.get("category", "")),       # optional metadata
                str(row.get("operating_hours", "")) # optional metadata
            ]
            combined_texts.append(" | ".join(parts))

        if combined_texts:
            combined_embeddings = self.embedding_model.encode(combined_texts, convert_to_numpy=True)
            dim = combined_embeddings.shape[1]
            combined_index = faiss.IndexFlatL2(dim)
            combined_index.add(combined_embeddings.astype("float32"))

            self.combined_embeddings = combined_embeddings
            self.combined_index = combined_index
            self.data["combined_text"] = combined_texts


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
                    "similarity": float(distances[0][rank]),
                    "tags": row.get("tags", ""),
                    "combined_text": row.get("combined_text", ""),
                    "rag_unit_id": self.id,
                    "rag_unit_name": self.name,
                })
        return results
    
    def query_combined(self, input_text: str, top_k: int = 5) -> List[dict]:
        """
        Query POIs using the combined embeddings (name + description + tags + metadata).
        """
        if self.combined_index is None or self.combined_embeddings is None:
            return []

        query_vec = self.embedding_model.encode([input_text], convert_to_numpy=True)
        query_vec = np.atleast_2d(query_vec).astype("float32")
        distances, indices = self.combined_index.search(query_vec, top_k)

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
                    "similarity": float(distances[0][rank]),
                    "tags": row.get("tags", ""),
                    "combined_text": row.get("combined_text", ""),
                    "rag_unit_id": self.id,
                    "rag_unit_name": self.name,
                })
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
    
    def get_vector(self, poi_name: str, field: str = "description") -> Optional[np.ndarray]:
        """
        Return the embedding vector for a POI by name.
        """
        if not hasattr(self, "name_to_idx"):
            return None

        idx = self.name_to_idx.get(normalize_name(poi_name))
        if idx is None:
            return None

        if field == "description":
            if self.description_embeddings is None:
                return None
            return self.description_embeddings[idx]

        if field == "combined":
            if self.combined_embeddings is None:
                return None
            return self.combined_embeddings[idx]

        raise NotImplementedError("Unsupported vector field requested")
                

class RAGPlatform:
    def __init__(self, rag_units: List[RAGUnit] = None):
        self.units: Dict[str, RAGUnit] = {unit.id: unit for unit in rag_units or []}

    def has_units(self) -> bool:
        return len(self.units) > 0

    def add_unit(self, unit: RAGUnit):
        self.units[unit.id] = unit
    
    def remove_unit_by_id(self, unit_id: str) -> bool:
        """
        Remove a RAGUnit from the platform by ID and refresh BallTree + dataframe.

        Args:
            unit_id (str): The ID of the unit to remove.

        Returns:
            bool: True if the unit was removed, False if not found.
        """
        if unit_id not in self.units:
            return False

        # Remove the unit
        del self.units[unit_id]

        # Refresh poi_df and balltree
        if self.has_units():
            self.balltree, self.balltree_df = self.build_balltree()
        else:
            # Reset if no units left
            self.balltree_df = None
            self.balltree = None

        return True

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
        return sorted(results, key=lambda x: x.get("similarity", float("inf")))[:top_k]

    def query_combined(self, query_text: str, top_k: int = 5) -> List[dict]:
        """
        Query POIs by the combined embedding vector (name + description + tags + metadata).
        """
        results = []
        for unit in self.units.values():
            try:
                index = getattr(unit, "combined_index", None)
                embeddings = getattr(unit, "combined_embeddings", None)
                if index is None or embeddings is None:
                    continue

                query_vec = unit.embedding_model.encode([query_text], convert_to_numpy=True)
                query_vec = np.atleast_2d(query_vec).astype("float32")
                distances, indices = index.search(query_vec, top_k)

                for rank, idx in enumerate(indices[0]):
                    if idx < len(unit.data):
                        row = unit.data.iloc[idx]
                        results.append({
                            "name": row.get("name", ""),
                            "description": row.get("description", ""),
                            "longitude": row.get("longitude"),
                            "latitude": row.get("latitude"),
                            "category": row.get("category", ""),
                            "tags": row.get("tags", ""),
                            "similarity": float(distances[0][rank]),
                            "source": unit.name,
                            "rag_unit_id": unit.id,
                            "rag_unit_name": unit.name,
                            "combined_text": row.get("combined_text", ""),
                        })
            except Exception as e:
                print(f"[{unit.id}] Error during combined query: {e}")
        return sorted(results, key=lambda x: x.get("similarity", float("inf")))[:top_k]
    
    def hybrid_query(self, query_text: str, top_k: int = 10, alpha: float = 0.5) -> List[dict]:
        """
        Hybrid retrieval combining:
        - description similarity
        - tag similarity
        - name similarity
        - combined vector similarity
        - lexical name matching fallback
        """
        norm_query = normalize_name(query_text)

        # --- Retrieve candidates ---
        desc_results = self.query_by_description(query_text, top_k * 4)
        tag_results = self.query_by_tags(query_text, top_k * 4)
        name_results = self.query_by_name(query_text, top_k * 4)
        combined_results = self.query_combined(query_text, top_k * 4)

        merged = {}

        # --- Aggregate scores ---
        for r in desc_results:
            merged[r["name"]] = {**r, "desc_score": 1.0 / (1 + r["similarity"]), "tag_score": 0.0, "name_score": 0.0, "combined_score": 0.0, "lexical_boost": 0.0}

        for r in tag_results:
            if r["name"] in merged:
                merged[r["name"]]["tag_score"] = 1.0 / (1 + r["similarity"])
            else:
                merged[r["name"]] = {**r, "desc_score": 0.0, "tag_score": 1.0 / (1 + r["similarity"]), "name_score": 0.0, "combined_score": 0.0, "lexical_boost": 0.0}

        for r in name_results:
            if r["name"] in merged:
                merged[r["name"]]["name_score"] = 1.0 / (1 + r["similarity"])
            else:
                merged[r["name"]] = {**r, "desc_score": 0.0, "tag_score": 0.0, "name_score": 1.0 / (1 + r["similarity"]), "combined_score": 0.0, "lexical_boost": 0.0}

        for r in combined_results:
            if r["name"] in merged:
                merged[r["name"]]["combined_score"] = 1.0 / (1 + r["similarity"])
            else:
                merged[r["name"]] = {**r, "desc_score": 0.0, "tag_score": 0.0, "name_score": 0.0, "combined_score": 1.0 / (1 + r["similarity"]), "lexical_boost": 0.0}

        # --- Lexical boost for exact name matches ---
        for r in merged.values():
            norm_name = normalize_name(r["name"])
            if norm_name in norm_query:
                r["lexical_boost"] = 2.0

        # --- Compute final hybrid score ---
        for r in merged.values():
            semantic_score = (
                alpha * r["desc_score"] +
                (1 - alpha) * r["tag_score"] +
                0.5 * r["name_score"] +
                0.7 * r["combined_score"]  # weight combined score fairly high
            )
            r["hybrid_score"] = semantic_score + r["lexical_boost"]

        # --- Return top-k ---
        results = sorted(merged.values(), key=lambda x: x["hybrid_score"], reverse=True)
        return results[:top_k]


    
    def build_balltree(self):
        """Build BallTree from all units' POI data and store internally."""
        all_pois = []
        for unit in self.units.values():
            try:
                df = unit.get_data().copy()  # <-- full dataframe with all columns
                df["rag_unit_id"] = unit.id
                df["rag_unit_name"] = unit.name
                # Make sure to drop rows with missing coordinates
                df = df.dropna(subset=["latitude", "longitude"])
                if not df.empty:
                    all_pois.append(df)
            except Exception as e:
                print(f"[{unit.id}] Failed to fetch location data: {e}")

        if not all_pois:
            raise ValueError("No POIs with valid coordinates found.")

        combined_df = pd.concat(all_pois, ignore_index=True)
        coords_rad = np.radians(combined_df[['latitude', 'longitude']].values)
        tree = BallTree(coords_rad, metric='haversine')

        self.balltree_df = combined_df  # now contains all POI columns
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
            list[dict]: Each dict contains the row of data corresponding to the POI name.
        """
        if self.balltree_df is None:
            raise ValueError("BallTree dataframe not initialized. Run build_balltree() first.")

        details = []
        for name in poi_names:
            row = self.balltree_df.loc[self.balltree_df['name'] == name]
            if row.empty:
                continue  # skip missing names (or raise if strict required)

            r = row.iloc[0]
            details.append(r)

        return details
    
    def get_poi_vector(self, poi_name: str, field: str = "description") -> Optional[np.ndarray]:
        for unit in self.units.values():
            vec = unit.get_vector(poi_name, field)
            if vec is not None:
                return vec
        return None
    
    def filter_by_category(self, category: str):
        """
        Return all POIs from all units that match the given category.

        Args:
            category (str): Category name to filter by.

        Returns:
            pd.DataFrame: Filtered POIs with matching category.
        """
        if self.balltree_df is None or self.balltree_df.empty:
            raise ValueError("No POIs available. Make sure BallTree dataframe is built.")

        filtered = self.balltree_df[self.balltree_df["category"].str.lower() == category.lower()]
        return filtered.reset_index(drop=True)
    
    def get_all_pois_as_dataframe(self):
        """
        Combine all POI dataframes from RAGUnits into one large dataframe.
        """
        import pandas as pd

        all_dfs = []
        for unit in self.units.values():
            try:
                df = unit.get_location_data()
                if not df.empty:
                    all_dfs.append(df)
            except Exception as e:
                print(f"[{unit.id}] Failed to fetch POIs: {e}")

        if not all_dfs:
            return pd.DataFrame(columns=[
                "id", "name", "category", "longitude", "latitude",
                "description", "operating_hours", "tags"
            ])

        return pd.concat(all_dfs, ignore_index=True)
    
    def get_bounds_from_balltree(self, padding_ratio: float = 0.02):
        """
        Return the geographic bounding box (min_lon, min_lat, max_lon, max_lat)
        for all POIs in degrees, with optional small padding.
        """
        if self.balltree_df is None or self.balltree_df.empty:
            raise ValueError("No POIs available to compute bounds")

        min_lon = self.balltree_df["longitude"].min()
        max_lon = self.balltree_df["longitude"].max()
        min_lat = self.balltree_df["latitude"].min()
        max_lat = self.balltree_df["latitude"].max()

        # Compute range-based padding (2% of range by default)
        lon_padding = (max_lon - min_lon) * padding_ratio
        lat_padding = (max_lat - min_lat) * padding_ratio

        return [
            [min_lon - lon_padding, min_lat - lat_padding],
            [max_lon + lon_padding, max_lat + lat_padding]
        ]
    
    def filter_pois_excluding(self, field: str, exclude_value: str) -> pd.DataFrame:
        """
        Return all POIs where the given field value is NOT equal to `exclude_value`.
        Example: filter_pois_excluding("category", "dining")
        """
        import pandas as pd

        df = self.get_all_pois_as_dataframe()
        if field not in df.columns:
            raise ValueError(f"Field '{field}' not found in POI data columns: {list(df.columns)}")

        # Handle both string and non-string comparisons robustly
        filtered_df = df[df[field].astype(str).str.lower() != str(exclude_value).lower()]
        return filtered_df.reset_index(drop=True)
