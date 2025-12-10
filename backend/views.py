import os
import uuid
import json
import traceback

from flask import Blueprint, request, jsonify, render_template, current_app as app, session, redirect, url_for
from werkzeug.utils import secure_filename
from pyvis.network import Network

import pandas as pd
import networkx as nx

from helpers.RAG import RAGPlatform, RAGUnit
from helpers.model import LLMPipeline
from helpers.config_store import (
    project_relative_path,
    PROJECT_ROOT
)
from helpers import account_store
from helpers.poi_graph_mapbox import (
    build_mapbox_poi_graph,
    build_mapbox_poi_graph_html,
    plan_route_through_pois,
)

backend_bp = Blueprint("backend", __name__)
RAG_UPLOAD_DIR = os.path.join(PROJECT_ROOT, "data", "rag_units")
os.makedirs(RAG_UPLOAD_DIR, exist_ok=True)
GRAPH_CACHE_PATH = os.path.join(PROJECT_ROOT, "graph", "poi_graph_cache.json")
os.makedirs(os.path.dirname(GRAPH_CACHE_PATH), exist_ok=True)


def _current_account_id():
    return session.get("user_id") or getattr(app, "active_account_id", None)


@backend_bp.before_request
def require_login():
    if session.get("user_id"):
        return
    accept_json = request.accept_mimetypes.accept_json and not request.accept_mimetypes.accept_html
    if accept_json:
        return jsonify({"error": "Unauthorized"}), 401
    return redirect(url_for("auth.login", next=request.url))


def persist_rag_units_config():
    rag: RAGPlatform = getattr(app, "rag", None)
    account_id = _current_account_id()
    if not rag or not account_id:
        return
    config = account_store.get_account_config(account_id)
    entries = []
    for unit in rag.units.values():
        source_path = unit.source.get("path", "")
        entries.append(
            {
                "id": unit.id,
                "name": unit.name,
                "description": getattr(unit, "description", ""),
                "source": {
                    "type": unit.source.get("type", "csv"),
                    "path": project_relative_path(source_path),
                },
            }
        )
    config["RAG_UNITS"] = entries
    account_store.update_account_config(account_id, config)
    if account_id == getattr(app, "active_account_id", None):
        app.reload_runtime_for_account(account_id)


def _get_mapbox_token():
    token = os.environ.get("MAPBOX_ACCESS_TOKEN") or ""
    if not token:
        raise ValueError("MAPBOX_ACCESS_TOKEN environment variable not set")
    return token


def _load_cached_graph():
    if not os.path.exists(GRAPH_CACHE_PATH):
        return None
    try:
        with open(GRAPH_CACHE_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        traceback.print_exc()
        return None


def _save_cached_graph(graph_data):
    try:
        with open(GRAPH_CACHE_PATH, "w", encoding="utf-8") as f:
            json.dump(graph_data, f)
    except Exception:
        traceback.print_exc()


def _clear_cached_graph():
    app.mapbox_graph = None
    app.graph_dirty = True
    try:
        os.remove(GRAPH_CACHE_PATH)
    except FileNotFoundError:
        pass
    except Exception:
        traceback.print_exc()


def _rebuild_mapbox_graph(write_html=False):
    if getattr(app, "poi_df", None) is None or app.poi_df.empty:
        _clear_cached_graph()
        return None

    token = _get_mapbox_token()
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


def _update_graph_after_data_change():
    app.graph_dirty = True
    try:
        _rebuild_mapbox_graph(write_html=True)
    except Exception:
        traceback.print_exc()


def _ensure_mapbox_graph(write_html=False):
    if getattr(app, "poi_df", None) is None or app.poi_df.empty:
        raise ValueError("POI dataframe not available")

    if getattr(app, "graph_dirty", False):
        return _rebuild_mapbox_graph(write_html=write_html)

    if getattr(app, "mapbox_graph", None) and not write_html:
        return app.mapbox_graph

    graph_data = None
    cached = _load_cached_graph()
    if cached:
        app.mapbox_graph = cached
        app.graph_dirty = False
        graph_data = cached
    else:
        graph_data = _rebuild_mapbox_graph(write_html=write_html)

    if graph_data is None:
        raise ValueError("Unable to build Mapbox graph")
    return graph_data


@backend_bp.route('/')
def backend_home():
    return render_template("layout.html")


@backend_bp.route('/screen/<screen_name>')
def screen_proxy(screen_name):
    screen_map = {
        "llm-manager": llm_manager,
        "rag-manager": rag_manager,
        "map-manager": map_manager,
        "analytics": analytics,
        "graph-viewer": map_graph,
        "live-panel": live_panel
    }
    if screen_name not in screen_map:
        return jsonify({"error": "Screen not found"}), 404
    return screen_map[screen_name]()


@backend_bp.route("/llm-manager")
def llm_manager():
    return render_template("screens/llm-manager.html")


@backend_bp.route("/rag-manager")
def rag_manager():
    return render_template("screens/rag-manager.html")


@backend_bp.route("/map-manager")
def map_manager():
    return render_template("screens/map-manager.html")


@backend_bp.route("/map_graph")
def map_graph():
    try:
        token = _get_mapbox_token()
    except ValueError as exc:
        token = ""
        print(f"[map_graph] warning: {exc}")
    return render_template("screens/map-graph.html", mapbox_token=token)


@backend_bp.route("/analytics")
def analytics():
    return render_template("screens/analytics.html")

@backend_bp.route("/live-panel")
def live_panel():
    return render_template("screens/live-panel.html")

############################################ CUSTOMIZATION UI ENDPOINTS #####################################################


@backend_bp.route("/init_rag", methods=["POST"])
def init_rag():
    """
    Initializes app.rag either from an uploaded CSV (creates a RAGPlatform with a single unit)
    or (optionally) from a provided prebuilt index (not implemented).
    """
    try:
        # CSV upload - create a RAGPlatform with one unit
        if 'csv' in request.files:
            csv_file = request.files['csv']
            if csv_file.filename == "":
                return jsonify(message="CSV file empty"), 400

            filename = secure_filename(csv_file.filename)
            storage_name = f"{uuid.uuid4()}_{filename}"
            path = os.path.join(RAG_UPLOAD_DIR, storage_name)
            csv_file.save(path)

            unit_id = str(uuid.uuid4())
            data_source = {"type": "csv", "path": path}
            new_unit = RAGUnit(id=unit_id, data_source=data_source, name=filename, description="Uploaded CSV")

            # Build platform and register
            platform = RAGPlatform(rag_units=[new_unit])
            app.rag = platform

            # Build balltree / poi df if method exists
            try:
                platform.build_balltree()
                app.poi_df = platform.balltree_df
                app.balltree = platform.balltree
                _update_graph_after_data_change()
            except Exception:
                # Not fatal, but warn
                traceback.print_exc()

            persist_rag_units_config()
            return jsonify(message="CSV loaded successfully", unit_id=unit_id), 200

        # If you want to support index-file initialization later, do it explicitly here
        elif 'index' in request.files:
            return jsonify(message="Index loading from file is not implemented. Please upload CSV."), 400

        return jsonify(message="No file provided"), 400

    except Exception as e:
        traceback.print_exc()
        return jsonify(message="Failed to initialize RAG", error=str(e)), 500


@backend_bp.route("/update_llm", methods=["POST"])
def update_llm():
    """
    Update or create an LLM pipeline and store as app.llm
    """
    data = request.get_json() or {}
    provider = data.get("provider")
    model = data.get("model")
    api_key = data.get("api_key")

    if not provider or not model:
        return jsonify(error="Both 'provider' and 'model' fields are required"), 400

    if provider.lower() != "huggingface" and not api_key:
        return jsonify(error=f"API key is required for provider '{provider}'"), 400

    try:
        llm_instance = LLMPipeline(provider=provider, model=model, api_key=api_key)
        app.llm = llm_instance
        account_id = _current_account_id()
        config = account_store.get_account_config(account_id)
        config["LLM_SETTINGS"] = {
            "provider": provider,
            "model": model,
            "api_key": api_key
        }
        config["LLM_PROVIDER"] = provider
        if model:
            config["GPT_MODEL"] = model
        if api_key:
            config["OPENAI_API_KEY"] = api_key
        account_store.update_account_config(account_id, config)
        if account_id == getattr(app, "active_account_id", None):
            app.reload_runtime_for_account(account_id)
        return jsonify(message="LLM pipeline updated successfully"), 200
    except Exception as e:
        traceback.print_exc()
        return jsonify(error=f"Failed to initialize LLM: {str(e)}"), 500

@backend_bp.route("/update_llm/persona", methods=["POST"])
def update_llm_persona():
    data = request.json
    custom_instructions = data.get("custom_instructions", "")

    # Save to your global config object
    app.llm_config["persona_instructions"] = custom_instructions
    account_id = _current_account_id()
    config = account_store.get_account_config(account_id)
    config["LLM_PERSONA"] = custom_instructions
    account_store.update_account_config(account_id, config)
    if account_id == getattr(app, "active_account_id", None):
        app.reload_runtime_for_account(account_id)

    return jsonify({"status": "ok"})

@backend_bp.route("/delete_unit", methods=["POST"])
def remove_rag_unit():
    """
    Remove a RAG unit by id and update POI dataframe + BallTree.
    """
    try:
        payload = request.get_json() or {}
        unit_id = payload.get('unit_id')
        if not unit_id:
            return jsonify({"error": "unit_id is required"}), 400

        rag: RAGPlatform = getattr(app, "rag", None)
        if rag is None:
            return jsonify({"error": "RAG platform not initialized"}), 400

        if unit_id not in rag.units:
            return jsonify({"error": f"RAG Unit {unit_id} not found."}), 404

        rag.remove_unit_by_id(unit_id)
        if rag.has_units():
            rag.balltree, app.balltree_df = rag.build_balltree()
            app.rag = rag
        else:
            app.poi_df = pd.DataFrame()
            app.balltree = None
        app.rag = rag
        _update_graph_after_data_change()
        persist_rag_units_config()
        return jsonify({"message": f"RAG Unit {unit_id} removed."}), 200

    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

@backend_bp.route("/add_unit", methods=["POST"])
def add_rag_unit():
    rag = app.rag
    name = request.form.get("unit_name")
    description = request.form.get("description", "")

    if not name:
        return jsonify({"error": "Unit name is required"}), 400

    # File validation
    file = request.files.get("file")
    if not file or not file.filename.endswith(".csv"):
        return jsonify({"error": "A valid CSV file is required"}), 400

    try:
        filename = secure_filename(file.filename)
        storage_name = f"{uuid.uuid4()}_{filename}"
        file_path = os.path.join(RAG_UPLOAD_DIR, storage_name)
        file.save(file_path)

        # Validate required columns
        import pandas as pd
        df = pd.read_csv(file_path)
        required_columns = [
            "name", "category", "longitude", "latitude",
            "description", "operating_hours", "tags"
        ]
        missing = [col for col in required_columns if col not in df.columns]
        if missing:
            return jsonify({"error": f"Missing required columns: {', '.join(missing)}"}), 400

        # Build the RAG unit
        data_source = {"type": "csv", "path": file_path}
        new_unit = RAGUnit(name=name, description=description, data_source=data_source)
        rag.add_unit(new_unit)
        rag.balltree, app.balltree_df = rag.build_balltree()
        app.rag = rag
        persist_rag_units_config()
        _update_graph_after_data_change()

        return jsonify({"message": f"CSV Unit '{new_unit.id}' added successfully"}), 200

    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


@backend_bp.route("/get_units", methods=["GET"])
def get_units():
    """
    Return list of units registered in the RAG platform.
    """
    rag: RAGPlatform = getattr(app, "rag", None)
    if rag is None:
        return jsonify(units=[])

    units = []
    for unit in rag.units.values():
        source_type = None
        try:
            source_type = unit.source.get("type", "unknown")
        except Exception:
            source_type = "unknown"

        units.append({
            "id": unit.id,
            "description": getattr(unit, "description", ""),
            "source_type": source_type,
            "name": getattr(unit, "name", "")
        })
    return jsonify(units=units), 200


@backend_bp.route("/rag_unit/<unit_id>/data", methods=["GET"])
def get_unit_data(unit_id):
    """
    Return the raw POI rows for a specific RAG unit so the UI can render a sheet-like editor.
    """
    rag: RAGPlatform = getattr(app, "rag", None)
    if rag is None:
        return jsonify({"error": "RAG platform not initialized"}), 400

    unit = rag.units.get(unit_id)
    if unit is None:
        return jsonify({"error": f"RAG Unit {unit_id} not found"}), 404

    df = unit.get_data()
    if df is None:
        return jsonify({"error": "Unit is missing a backing dataframe"}), 400

    payload = {
        "unit": {
            "id": unit.id,
            "name": unit.name,
            "description": unit.description,
            "source_path": unit.source.get("path", "")
        },
        "columns": df.columns.tolist(),
        "rows": df.fillna("").to_dict(orient="records")
    }
    return jsonify(payload), 200


@backend_bp.route("/rag_unit/<unit_id>/data", methods=["PUT"])
def update_unit_data(unit_id):
    """
    Persist edits to a unit's CSV file and refresh in-memory indices/ball-trees.
    """
    rag: RAGPlatform = getattr(app, "rag", None)
    if rag is None:
        return jsonify({"error": "RAG platform not initialized"}), 400

    unit = rag.units.get(unit_id)
    if unit is None:
        return jsonify({"error": f"RAG Unit {unit_id} not found"}), 404

    payload = request.get_json() or {}
    rows = payload.get("rows")
    columns = payload.get("columns")

    if rows is None:
        return jsonify({"error": "rows payload required"}), 400

    df = pd.DataFrame(rows)
    if columns:
        # Preserve column order and ensure missing keys exist
        for col in columns:
            if col not in df.columns:
                df[col] = ""
        df = df[columns]
    else:
        columns = df.columns.tolist()

    csv_path = unit.source.get("path")
    if not csv_path:
        return jsonify({"error": "Unit does not track a CSV file path"}), 400

    try:
        df.to_csv(csv_path, index=False)
    except Exception as exc:
        return jsonify({"error": f"Failed to write CSV: {exc}"}), 500

    unit.data = df
    try:
        unit.build_indices()
    except Exception as exc:
        return jsonify({"error": f"Failed to rebuild indices: {exc}"}), 500

    rag.units[unit.id] = unit

    try:
        balltree, poi_df = rag.build_balltree()
        app.balltree = balltree
        app.poi_df = poi_df
    except Exception as exc:
        return jsonify({"error": f"POI spatial index refresh failed: {exc}"}), 500

    try:
        app.graph = rag.build_graph()
    except Exception:
        # Graph is optional; keep failure non-fatal but log for debugging.
        traceback.print_exc()

    app.rag = rag
    _update_graph_after_data_change()
    return jsonify({"message": "POI data updated", "columns": columns}), 200

@backend_bp.route('/update_map_style', methods=['POST'])
def update_map_style():
    data = request.get_json() or {}
    new_style_url = data.get("mapbox_style_url")
    new_map_centre = data.get("map_centre")
    has_polygon_payload = "spotlight_polygon" in data
    new_spotlight_polygon = data.get("spotlight_polygon")

    if not new_style_url and not new_map_centre and not has_polygon_payload:
        return jsonify({"error": "No data provided for update"}), 400

    def _validate_polygon(polygon_obj):
        if not isinstance(polygon_obj, dict):
            return False
        if polygon_obj.get("type") != "Polygon":
            return False
        coords = polygon_obj.get("coordinates")
        if not isinstance(coords, list) or not coords:
            return False
        outer_ring = coords[0]
        if not isinstance(outer_ring, list) or len(outer_ring) < 3:
            return False
        for point in outer_ring:
            if (
                not isinstance(point, (list, tuple))
                or len(point) != 2
                or any(coord is None for coord in point)
            ):
                return False
        return True

    try:
        account_id = _current_account_id()
        config = account_store.get_account_config(account_id)

        if new_style_url:
            config["MAPBOX_STYLE_URL"] = new_style_url

        if new_map_centre:
            if not isinstance(new_map_centre, list) or len(new_map_centre) != 2:
                return jsonify({"error": "Invalid map_centre format"}), 400
            lng = float(new_map_centre[0])
            lat = float(new_map_centre[1])
            config["MAP_CENTRE"] = json.dumps([lng, lat])

        if has_polygon_payload:
            if new_spotlight_polygon is None:
                config.pop("MAP_SPOTLIGHT_POLYGON", None)
            else:
                if not _validate_polygon(new_spotlight_polygon):
                    return jsonify({"error": "Invalid spotlight polygon"}), 400
                config["MAP_SPOTLIGHT_POLYGON"] = json.dumps(new_spotlight_polygon)

        account_store.update_account_config(account_id, config)
        if account_id == getattr(app, "active_account_id", None):
            app.reload_runtime_for_account(account_id)
        return jsonify({
            "message": "Map settings updated",
            "style_url": config.get("MAPBOX_STYLE_URL"),
            "map_centre": json.loads(config.get("MAP_CENTRE")) if config.get("MAP_CENTRE") else None,
            "spotlight_polygon": json.loads(config.get("MAP_SPOTLIGHT_POLYGON")) if config.get("MAP_SPOTLIGHT_POLYGON") else None
        }), 200

    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

@backend_bp.route("/graph")
def show_graph():
    """
    Build the Mapbox-based POI graph from the current POI dataframe
    and save it as templates/graph.html, then render it.
    """
    try:
        _ensure_mapbox_graph(write_html=True)
        return render_template("graph.html")

    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


@backend_bp.route("/rebuild_graph", methods=["POST"])
def rebuild_graph():
    """
    Force rebuild of the Mapbox POI graph using all POIs from all RAG units.
    """
    try:
        if getattr(app, "rag", None) is None or not app.rag.units:
            return jsonify({"error": "No RAG units available to rebuild graph."}), 400

        # Combine all POIs from every RAG unit
        all_pois = []
        for unit in app.rag.units.values():
            df = unit.get_data()
            if df is not None:
                df = df.dropna(subset=["latitude", "longitude"])
                all_pois.append(df)

        if not all_pois:
            return jsonify({"error": "No POIs available to rebuild graph."}), 400

        combined_df = pd.concat(all_pois, ignore_index=True)
        app.poi_df = combined_df

        # Rebuild graph and cache
        _ensure_mapbox_graph(write_html=True)
        return jsonify({"message": "Graph rebuilt successfully."})

    except Exception as exc:
        traceback.print_exc()
        return jsonify({"error": str(exc)}), 500
@backend_bp.route("/graph_data")
def get_graph_data():
    """
    Return GeoJSON-like structure of nodes + edges from the Mapbox graph for client-side rendering.
    """
    try:
        graph_data = _ensure_mapbox_graph()
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    except Exception as exc:
        traceback.print_exc()
        return jsonify({"error": str(exc)}), 500

    nodes = []
    edges = []
    node_lookup = {}

    for node in graph_data.get("nodes", []):
        lon = node.get("longitude")
        lat = node.get("latitude")
        name = node.get("name")
        node_lookup[name] = (lon, lat)
        nodes.append({
            "type": "Feature",
            "geometry": {
                "type": "Point",
                "coordinates": [lon, lat]
            },
            "properties": {
                "name": name,
                "feature_type": "node"
            }
        })

    for edge in graph_data.get("edges", []):
        u = edge.get("from")
        v = edge.get("to")
        geometry = edge.get("geometry")
        if not geometry:
            u_pos = node_lookup.get(u)
            v_pos = node_lookup.get(v)
            if not u_pos or not v_pos:
                continue
            geometry = [list(u_pos), list(v_pos)]

        edges.append({
            "type": "Feature",
            "geometry": {
                "type": "LineString",
                "coordinates": geometry
            },
            "properties": {
                "from": u,
                "to": v,
                "distance_m": edge.get("distance_m"),
                "duration_s": edge.get("duration_s"),
                "fallback": edge.get("fallback", False),
                "feature_type": "edge"
            }
        })

    geojson = {
        "type": "FeatureCollection",
        "features": nodes + edges
    }

    return jsonify(geojson)


@backend_bp.route("/plan_route", methods=["POST"])
def plan_route_api():
    try:
        payload = request.get_json() or {}
        poi_names = payload.get("poi_names") or []
        if not isinstance(poi_names, list) or len(poi_names) < 2:
            return jsonify({"error": "Provide at least two POI names in 'poi_names'."}), 400

        graph_data = _ensure_mapbox_graph()
        plan = plan_route_through_pois(
            poi_names,
            graph_data["nodes"],
            graph_data["edges"],
            app.poi_df,
        )
        return jsonify(plan)

    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    except Exception as exc:
        traceback.print_exc()
        return jsonify({"error": str(exc)}), 500
