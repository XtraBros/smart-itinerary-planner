import json
import os
import traceback
from typing import Optional, Dict

from helpers.config_store import PROJECT_ROOT
from helpers.poi_graph_mapbox import build_mapbox_poi_graph, build_mapbox_poi_graph_html

GRAPH_CACHE_PATH = os.path.join(PROJECT_ROOT, "graph", "poi_graph_cache.json")
os.makedirs(os.path.dirname(GRAPH_CACHE_PATH), exist_ok=True)


def get_mapbox_token() -> str:
    token = os.environ.get("MAPBOX_ACCESS_TOKEN") or ""
    if not token:
        raise ValueError("MAPBOX_ACCESS_TOKEN environment variable not set")
    return token


def _load_cached_graph() -> Optional[Dict]:
    if not os.path.exists(GRAPH_CACHE_PATH):
        return None
    try:
        with open(GRAPH_CACHE_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        traceback.print_exc()
        return None


def _save_cached_graph(graph_data: Dict) -> None:
    try:
        with open(GRAPH_CACHE_PATH, "w", encoding="utf-8") as f:
            json.dump(graph_data, f)
    except Exception:
        traceback.print_exc()


def clear_cached_graph(app) -> None:
    app.mapbox_graph = None
    app.graph_dirty = True
    try:
        os.remove(GRAPH_CACHE_PATH)
    except FileNotFoundError:
        pass
    except Exception:
        traceback.print_exc()


def rebuild_mapbox_graph(app, write_html: bool = False):
    if getattr(app, "poi_df", None) is None or app.poi_df.empty:
        clear_cached_graph(app)
        return None

    token = get_mapbox_token()

    if write_html:
        output_path = os.path.join("templates", "graph.html")
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        graph_data = build_mapbox_poi_graph_html(app.poi_df, output_path, mapbox_token=token)
    else:
        nodes, edges = build_mapbox_poi_graph(app.poi_df, mapbox_token=token)
        graph_data = {"nodes": nodes, "edges": edges}

    _save_cached_graph(graph_data)
    app.mapbox_graph = graph_data
    app.graph_dirty = False
    return graph_data


def ensure_mapbox_graph(app, write_html: bool = False):
    if write_html:
        return rebuild_mapbox_graph(app, write_html=True)

    if getattr(app, "graph_dirty", False):
        return rebuild_mapbox_graph(app, write_html=False)

    if getattr(app, "mapbox_graph", None):
        return app.mapbox_graph

    cached = _load_cached_graph()
    if cached:
        app.mapbox_graph = cached
        app.graph_dirty = False
        return cached

    return rebuild_mapbox_graph(app, write_html=False)


def update_graph_after_data_change(app) -> None:
    app.graph_dirty = True
    try:
        rebuild_mapbox_graph(app, write_html=True)
    except Exception:
        traceback.print_exc()
