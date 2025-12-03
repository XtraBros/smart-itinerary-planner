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

backend_bp = Blueprint("backend", __name__)
RAG_UPLOAD_DIR = os.path.join(PROJECT_ROOT, "data", "rag_units")
os.makedirs(RAG_UPLOAD_DIR, exist_ok=True)


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
    return render_template("screens/map-graph.html")


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
    Render the pyvis graph of app.graph (created from BallTree).
    Saves HTML under templates/screens/graph.html for rendering.
    """
    try:
        if not hasattr(app, "graph") or app.graph is None:
            return jsonify({"error": "Graph not built"}), 400

        net = Network(height="600px", width="100%", bgcolor="#222222", font_color="white")
        SCALE_X = 100000
        SCALE_Y = 100000

        if getattr(app, "poi_df", None) is None:
            return jsonify({"error": "POI dataframe not available"}), 400

        min_lon = app.poi_df['longitude'].min()
        min_lat = app.poi_df['latitude'].min()

        for _, row in app.poi_df.iterrows():
            name = row["name"]
            lon = (row["longitude"] - min_lon) * SCALE_X
            lat = (row["latitude"] - min_lat) * SCALE_Y
            net.add_node(n_id=name, label=name, title=name, x=lon, y=-lat, fixed=True)

        for u, v, data in app.graph.edges(data=True):
            weight = data.get("weight", 1)
            net.add_edge(u, v, value=weight, title=f"{weight:.0f}m")

        net.toggle_physics(False)

        output_path = os.path.join("templates", "screens", "graph.html")
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        net.save_graph(output_path)

        return render_template("screens/graph.html")

    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

@backend_bp.route("/graph_data")
def get_graph_data():
    """
    Return GeoJSON-like structure of nodes + edges from app.graph for client-side rendering.
    """
    if not hasattr(app, "graph") or app.graph is None:
        return jsonify({"error": "Graph not built"}), 400

    nodes = []
    edges = []

    for node_name, attrs in app.graph.nodes(data=True):
        lon, lat = attrs.get('pos', (None, None))
        nodes.append({
            "type": "Feature",
            "geometry": {
                "type": "Point",
                "coordinates": [lon, lat]
            },
            "properties": {
                "name": node_name
            }
        })

    for u, v, data in app.graph.edges(data=True):
        u_pos = app.graph.nodes[u]['pos']
        v_pos = app.graph.nodes[v]['pos']
        edges.append({
            "type": "Feature",
            "geometry": {
                "type": "LineString",
                "coordinates": [
                    [u_pos[0], u_pos[1]],
                    [v_pos[0], v_pos[1]]
                ]
            },
            "properties": {
                "from": u,
                "to": v,
                "weight": data.get("weight", 1)
            }
        })

    geojson = {
        "type": "FeatureCollection",
        "features": nodes + edges
    }

    return jsonify(geojson)
