from typing import List, Dict, Optional
from sentence_transformers import SentenceTransformer
from numpy import dot
from numpy.linalg import norm


def cosine_similarity(v1, v2):
    return dot(v1, v2) / (norm(v1) * norm(v2) + 1e-8)


class RetrievalPolicyManager:
    def __init__(self, rag_platform):
        self.rag = rag_platform
        self.embedding_model = SentenceTransformer("all-MiniLM-L6-v2")

    # ============================================================
    # Preference → Query Modifier
    # ============================================================
    def _make_preference_query(self, query_text: str, preferences: dict) -> str:
        """
        Convert user preferences into a modifier for semantic search.
        Only relevant fields are included.
        """

        pref_parts = []

        if preferences.get("interests"):
            pref_parts.append(f"interests: {', '.join(preferences['interests'])}")

        if preferences.get("total_time"):
            pref_parts.append(f"total_time: {preferences['total_time']}")

        if not pref_parts:
            return query_text

        pref_text = " | ".join(pref_parts)

        return f"User preferences: {pref_text}. Query: {query_text}"

    # ============================================================
    # Preference score: categories, tags, metadata
    # ============================================================
    def _preference_score(self, poi: Dict, preferences: dict) -> float:
        """
        Compute a simple preference match score for reranking.
        """

        score = 0.0

        # interests → match with metadata/tags/categories
        interests = preferences.get("interests", [])

        if interests:
            text_parts = []
            category = poi.get("category")
            if category:
                text_parts.append(str(category))

            tags = poi.get("tags")
            if tags:
                if isinstance(tags, (list, tuple, set)):
                    text_parts.extend(str(tag) for tag in tags)
                else:
                    text_parts.append(str(tags))

            description = poi.get("description")
            if description:
                text_parts.append(description)

            combined_text = poi.get("combined_text")
            if combined_text:
                text_parts.append(str(combined_text))

            text_blob = " ".join(text_parts).lower()

            for interest in interests:
                if interest.lower() in text_blob:
                    score += 1.0   # +1 for each match

        # total_time → match optional metadata (optional)
        if "total_time" in preferences:
            pass  # You can later map time to POI duration

        return score

    # ============================================================
    # Main Dispatcher
    # ============================================================
    def decide_retrieval(
        self,
        query_text: Optional[str] = None,
        lat: Optional[float] = None,
        lon: Optional[float] = None,
        preferences: Optional[Dict] = None,
        radius_km: Optional[float] = 0.5,
        top_k: int = 5,
        intent: str = "generic",
    ) -> List[Dict]:

        preferences = preferences or {}

        # modify query with preferences
        enriched_query = self._make_preference_query(query_text, preferences)

        if intent == "spatial":
            return self._spatial_flow(lat, lon, enriched_query, top_k, radius_km, preferences)

        elif intent == "semantic":
            return self._semantic_flow(enriched_query, top_k, preferences)

        elif intent == "hybrid":
            return self._hybrid_flow(lat, lon, enriched_query, top_k, radius_km, preferences)

        # elif intent == "navigation":
        #     return self._navigation_flow(enriched_query)

        else:
            raise ValueError(f"Unknown intent: {intent}")

    # ============================================================
    # SPATIAL FLOW
    # ============================================================
    def _spatial_flow(self, lat, lon, query_text, top_k, radius_km, preferences):
        spatial = self.rag.spatial_query(lat, lon, k=50, radius_km=radius_km)

        # rerank with semantic + preferences
        return self._rerank(spatial, query_text, top_k, preferences, use_distance=True)

    # ============================================================
    # SEMANTIC FLOW
    # ============================================================
    def _semantic_flow(self, query_text, top_k, preferences):
        semantic = self.rag.query_combined(query_text, top_k=top_k*2)
        return self._rerank(semantic, query_text, top_k, preferences)

    # ============================================================
    # HYBRID FLOW
    # ============================================================
    def _hybrid_flow(self, lat, lon, query_text, top_k, radius_km, preferences):
        spatial = self.rag.spatial_query(lat, lon, k=30, radius_km=radius_km)
        semantic = self.rag.query_combined(query_text, top_k=30)
        merged = spatial + semantic
        return self._rerank(merged, query_text, top_k, preferences, use_distance=True)

    # ============================================================
    # Lightweight reranker (semantic + preferences + spatial)
    # ============================================================
    def _rerank(self, candidates, query_text, top_k, preferences, use_distance=False):
        query_vec = self.embedding_model.encode(query_text)

        scored = []

        for poi in candidates:
            poi_vec = poi.get("combined_vector")
            if poi_vec is None:
                unit_id = poi.get("rag_unit_id")
                poi_name = poi.get("name")
                unit = self.rag.units.get(unit_id) if unit_id else None
                if unit and poi_name:
                    poi_vec = unit.get_vector(poi_name, field="combined")
            if poi_vec is None:
                continue

            semantic_sim = cosine_similarity(query_vec, poi_vec)

            pref_score = self._preference_score(poi, preferences)

            spatial_score = 0.0
            if use_distance and "distance_km" in poi:
                spatial_score = 1 / (1 + poi["distance_km"])

            final = (0.6 * semantic_sim) + (0.2 * pref_score) + (0.2 * spatial_score)

            scored.append({**poi, "final_score": final})

        return sorted(scored, key=lambda x: x["final_score"], reverse=True)[:top_k]

    # ============================================================
    # NAVIGATION (incomplete )
    # ============================================================
    # def _navigation_flow(self, query_text):
    #     return {"navigation_query": query_text}
