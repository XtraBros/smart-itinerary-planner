from typing import List, Dict, Optional
import numpy as np
from sentence_transformers import SentenceTransformer
from numpy import dot
from numpy.linalg import norm

def cosine_similarity(vec1, vec2):
    return dot(vec1, vec2) / (norm(vec1) * norm(vec2))

class RetrievalPolicyManager:
    def __init__(self, rag_platform):
        self.rag = rag_platform
        self.embedding_model = SentenceTransformer("all-MiniLM-L6-v2")

    def decide_retrieval(
        self, 
        query_text: Optional[str] = None,
        lat: Optional[float] = None, 
        lon: Optional[float] = None,
        radius_km: Optional[float] = 0.5,
        top_k: int = 5,
        intent: str = "generic",  # "generic", "spatial", "hybrid"
    ) -> List[Dict]:
        """
        Dispatch retrieval strategy based on intent.
        """
        if intent == "spatial":
            return self._spatial_flow(lat, lon, query_text, top_k, radius_km)
        elif intent == "hybrid":
            return self._hybrid_flow(query_text, lat, lon, top_k, radius_km)
        elif intent == "semantic":
            return self._semantic_flow(query_text, lat, lon, top_k, radius_km)
        else:
            raise ValueError(f"Unknown intent: {intent}")

    # ---------------- Flows ---------------- #
    def _spatial_flow(self, lat, lon, query_text, top_k, radius_km):
        # Step 1: Spatial prefilter
        spatial_results = self.rag.spatial_query(lat, lon, k=50, radius_km=radius_km)
        # Step 2: Rerank if query_text present
        if query_text:
            return self._rerank_semantic(spatial_results, query_text, top_k, alpha=0.3)
        return spatial_results

    def _semantic_flow(self, query_text, lat, lon, top_k, radius_km):
        # Step 1: Semantic search
        semantic_results = self.rag.hybrid_query(query_text, top_k=top_k*2)

        # Step 2: Filter by distance if user location given
        if lat and lon and radius_km:
            semantic_results = [
                r for r in semantic_results 
                if r.get("distance_km", float("inf")) <= radius_km
            ]
        return semantic_results[:top_k]

    def _hybrid_flow(self, query_text, lat, lon, top_k, radius_km):
        # Step 1: Get spatial candidates
        spatial = self.rag.spatial_query(lat, lon, k=30, radius_km=radius_km)
        # Step 2: Get semantic candidates
        semantic = self.rag.hybrid_query(query_text, top_k=30)
        # Step 3: Fuse
        return self._fuse(spatial, semantic, top_k, alpha=0.6)

    # ---------------- Utils ---------------- #
    def _rerank_semantic(self, candidates, query_text, top_k, alpha=0.3):
        """
        Rerank spatial results with semantic similarity.
        """
        query_emb = self.embedding_model.encode(query_text)
        reranked = []
        for r in candidates:
            # Run semantic query_by_description for rerank
            # (or could do lightweight embedding similarity)
            poi_vector = self.rag.get_poi_vector(r["name"].lower(), field="description")
            sim = cosine_similarity(query_emb, poi_vector)
            r["rerank_score"] = alpha * (1/(1+sim)) + (1-alpha) * (1/(1+r["distance_km"]))
            reranked.append(r)
        return sorted(reranked, key=lambda x: x["rerank_score"], reverse=True)[:top_k]

    def _fuse(self, spatial, semantic, top_k, alpha=0.6):
        """
        Merge spatial + semantic results with hybrid scoring.
        """
        merged = {}
        for r in spatial:
            merged[r["name"]] = {**r, "spatial_score": 1/(1+r["distance_km"]), "semantic_score": 0.0}
        for r in semantic:
            if r["name"] in merged:
                merged[r["name"]]["semantic_score"] = 1/(1+r["similarity"])
            else:
                merged[r["name"]] = {**r, "spatial_score": 0.0, "semantic_score": 1/(1+r["similarity"])}

        for v in merged.values():
            v["final_score"] = alpha * v["semantic_score"] + (1-alpha) * v["spatial_score"]

        return sorted(merged.values(), key=lambda x: x["final_score"], reverse=True)[:top_k]
