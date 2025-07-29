from flask import Blueprint, request, jsonify, render_template, current_app as app
from . import backend_bp
from helpers.RAG import RAGPlatform, RAGUnit
import os
from pyvis.network import Network
import json
from werkzeug.utils import secure_filename
from helpers.route_solver import update_ball_tree
from helpers.model import LLMPipeline

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
        "map-graph": map_graph
    }
    if screen_name not in screen_map:
        return jsonify({"error": "Screen not found"}), 404
    return screen_map[screen_name]()

@backend_bp.route("/llm-manager")
def llm_manager():
    # Add logic if needed
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


############################################ CUSTOMIZATION UI ENDPOINTS #####################################################
@backend_bp.route("/init_rag", methods=["POST"])
def init_rag():
    try:
        if 'csv' in request.files:
            csv_file = request.files['csv']
            # Pass file-like object directly, no need to save to disk
            rag_instance = RAGPlatform(csv_file=csv_file)
            app.rag = rag_instance
            return jsonify(message="CSV loaded successfully")
        elif 'index' in request.files:
            index_file = request.files['index']
            index_file.save("index.faiss")  # Still need to save since loading from file is not implemented
            rag_instance = RAGPlatform(index_file="index.faiss")
            app.rag = rag_instance
            return jsonify(message="Index loaded successfully")
        return jsonify(message="No file provided"), 400
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify(message="Failed to initialize RAG", error=str(e)), 500

@backend_bp.route("/update_llm", methods=["POST"])
def update_llm():
    global llm_instance
    data = request.get_json()

    provider = data.get("provider")
    model = data.get("model")
    api_key = data.get("api_key")

    if not provider or not model:
        return jsonify(error="Both 'provider' and 'model' fields are required"), 400

    # Require API key for all providers except 'huggingface'
    if provider.lower() != "huggingface" and not api_key:
        return jsonify(error=f"API key is required for provider '{provider}'"), 400

    # Initialize the LLM pipeline
    try:
        llm_instance = LLMPipeline(
            provider=provider,
            model=model,
            api_key=api_key
        )
        app.llm = llm_instance
        return jsonify(message="LLM pipeline updated successfully")
    except Exception as e:
        return jsonify(error=f"Failed to initialize LLM: {str(e)}"), 500

@backend_bp.route("/delete_unit", methods=["POST"])
def remove_rag_unit():
    rag = app.rag
    unit_id = request.json['unit_id']
    print(unit_id)
    if unit_id in rag.units:
        app.remove_unit_by_id(unit_id)

        # === HERE: Update app.poi_df and balltree ===
        app.poi_df = rag.get_all_pois_as_dataframe()
        app.balltree = update_ball_tree(app.poi_df)
        app.rag = rag
        return jsonify({"message": f"RAG Unit {unit_id} removed."}), 200
    return jsonify({"error": f"RAG Unit {unit_id} not found."}), 404


@backend_bp.route("/add_unit", methods=["POST"])
def add_rag_unit():
    rag = app.rag
    source_type = request.form.get("source")
    name = request.form.get("unit_name")
    description = request.form.get("description", "")

    if not name:
        return jsonify({"error": "Unit name is required"}), 400

    temp_dir = "/tmp"
    os.makedirs(temp_dir, exist_ok=True)

    try:
        if source_type in ["csv", "json", "excel", "index"]:
            file = request.files.get("file")
            if not file:
                return jsonify({"error": f"{source_type.upper()} file not provided"}), 400

            filename = secure_filename(file.filename)
            file_path = os.path.join(temp_dir, filename)
            file.save(file_path)

            actual_type = source_type if source_type != "index" else "csv"

            data_source = {
                "type": actual_type,
                "path": file_path
            }

        elif source_type == "mongodb":
            mongo_uri = request.form.get("mongo_url")
            mongo_db = request.form.get("mongo_db")
            mongo_collection = request.form.get("mongo_collection")
            if not all([mongo_uri, mongo_db, mongo_collection]):
                return jsonify({"error": "MongoDB URI, DB name and collection are required"}), 400

            data_source = {
                "type": "mongo",
                "uri": mongo_uri,
                "db": mongo_db,
                "collection": mongo_collection
            }

        elif source_type == "sql":
            host = request.form.get("host")
            port = request.form.get("port")
            user = request.form.get("user")
            password = request.form.get("password")
            database = request.form.get("database")
            query = request.form.get("query")

            if not all([host, database, query]):
                return jsonify({"error": "SQL host, database, and query are required"}), 400

            data_source = {
                "type": "sql",
                "host": host,
                "port": port,
                "user": user,
                "password": password,
                "database": database,
                "query": query
            }

        elif source_type == "cms":
            api_url = request.form.get("api_url")
            auth_token = request.form.get("auth_token")
            if not api_url:
                return jsonify({"error": "CMS API URL is required"}), 400

            data_source = {
                "type": "cms",
                "api_url": api_url,
                "auth": {"token": auth_token} if auth_token else None
            }

        else:
            return jsonify({"error": f"Unsupported source type '{source_type}'"}), 400

        # Create and build the unit
        new_unit = RAGUnit(name=name, description=description, data_source=data_source)
        rag.add_unit(new_unit)

        # === HERE: Update app.poi_df and balltree ===
        app.poi_df = rag.get_all_pois_as_dataframe()
        app.balltree = update_ball_tree(app.poi_df)
        app.rag = rag
        return jsonify({"message": f"Unit added with ID {new_unit.id}"}), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@backend_bp.route("/get_units", methods=["GET"])
def get_units():
    units = []
    for unit in app.rag.units.values():
        units.append({
            "id": unit.id,
            "description": unit.description,
            "source_type": unit.source.get("type", "unknown"),
            "name": unit.name
        })
    return jsonify(units=units)


@backend_bp.route('/update_map_style', methods=['POST'])
def update_map_style():
    def load_config():
        with open('../config.json') as f:
            return json.load(f)

    def save_config(data):
        with open('../config.json', 'w') as f:
            json.dump(data, f, indent=2)
    data = request.json
    new_style_url = data.get("mapbox_style_url")
    new_map_centre = data.get("map_centre")

    if not new_style_url and not new_map_centre:
        return jsonify({"error": "No data provided for update"}), 400

    config = load_config()

    if new_style_url:
        config["MAPBOX_STYLE_URL"] = new_style_url

    if new_map_centre:
        if not isinstance(new_map_centre, list) or len(new_map_centre) != 2:
            return jsonify({"error": "Invalid map_centre format"}), 400
        try:
            lng = float(new_map_centre[0])
            lat = float(new_map_centre[1])
            config["MAP_CENTRE"] = json.dumps([lng, lat])  # Save as stringified list
        except ValueError:
            return jsonify({"error": "Map centre must be numeric"}), 400

    save_config(config)

    return jsonify({
        "message": "Map settings updated",
        "style_url": config.get("MAPBOX_STYLE_URL"),
        "map_centre": config.get("MAP_CENTRE")
    })

@backend_bp.route("/graph")
def show_graph():
    net = Network(height="600px", width="100%", bgcolor="#222222", font_color="white")

    # Scale factor to spread out nodes visually
    SCALE_X = 100000
    SCALE_Y = 100000

    min_lon = app.poi_df['longitude'].min()
    min_lat = app.poi_df['latitude'].min()

    for _, row in app.poi_df.iterrows():
        name = row["name"]
        lon = (row["longitude"] - min_lon) * SCALE_X
        lat = (row["latitude"] - min_lat) * SCALE_Y
        net.add_node(n_id=name, label=name, title=name, x=lon, y=-lat, fixed=True)

    # Add edges with distance as weight
    for u, v, data in app.graph.edges(data=True):
        weight = data.get("weight", 1)
        net.add_edge(u, v, value=weight, title=f"{weight:.0f}m")

    # Disable physics so coordinates remain fixed
    net.toggle_physics(False)

    # Save to static folder instead of templates
    output_path = os.path.join("templates", "graph.html")
    net.save_graph(output_path)

    return render_template("graph.html")


@backend_bp.route("/graph_data")
def get_graph_data():
    nodes = []
    edges = []

    for node in app.graph.nodes(data=True):
        name = node[0]
        lon, lat = node[1]['pos']
        nodes.append({
            "type": "Feature",
            "geometry": {
                "type": "Point",
                "coordinates": [lon, lat]
            },
            "properties": {
                "name": name
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