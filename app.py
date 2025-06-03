from flask import Flask, render_template, request, jsonify, redirect, url_for
import pandas as pd
import json
from langchain.memory import ConversationBufferWindowMemory
import ast
from helpers.text_processing import *
from helpers.prompts import *
from helpers.RAG import *
from helpers.route_solver import *
from helpers.planner import *
from helpers.model import LLMPipeline
from werkzeug.utils import secure_filename
from pyvis.network import Network

app = Flask(__name__)

CONFIG_FILE = 'config.json'

with open(CONFIG_FILE, 'r') as file:
    config = json.load(file)

######################### LLM INIT #########################
llm = LLMPipeline(provider='openai', model=config['GPT_MODEL'], api_key=config['OPENAI_API_KEY'])
# Initialize memory for conversation
memory = ConversationBufferWindowMemory(k=3, memory_key="history")
######################### RAG Data #########################
# Load POI List from csv file:
place_info = pd.read_csv("./zoo-info.csv")
# Table columns: [floor, floorId, icon, location, name, poiId, unit]
place_info_df = pd.DataFrame(place_info)
# name_to_poiId = dict(zip(place_info_df["name"], place_info_df["poiId"]))
# poiId_to_name = dict(zip(place_info_df["poiId"], place_info_df["name"]))
# categories = place_info_df['category'].unique().tolist()
unit1 = RAGUnit(
    data_source={"type": "csv", "path": "./zoo-info.csv"},
    description="Zoo info CSV",
    name= "Mandai Zoo CSV"
)
unit2= RAGUnit(
    data_source={"type": "csv", "path": "./sentosa.csv"},
    description="Sentosa POI CSV",
    name= "Sentosa Island CSV"
)
rag = RAGPlatform([unit2])
balltree, poi_df = build_balltree_from_rag_platform(rag)
graph = build_graph_from_balltree(poi_df, balltree, np.radians(poi_df[['latitude', 'longitude']].values), k=5)
app.balltree = balltree
app.poi_df = poi_df
######################### MISC init #########################
api_url = config['API_URL']
locale_name = "Sentosa Island"
# Change place list to poi name list
locale_place_list = place_info_df['name'].tolist()

@app.route('/')
def home():
    return render_template('index.html', places=place_info_df)

# Helper to load and save config
def load_config():
    with open(CONFIG_FILE) as f:
        return json.load(f)

def save_config(data):
    with open(CONFIG_FILE, 'w') as f:
        json.dump(data, f, indent=2)

@app.route('/config', methods=['GET'])
def get_config():
    config = load_config()
    return jsonify({'config': config})

@app.route('/ops_router', methods=['POST'])
def ops_router():
    user_input = request.json['message']
    conversation_history = memory.load_memory_variables({})
    history = process_formatted_history(conversation_history.get('history', ''))
    prompt = f"""
    You are a routing agent in a chat-based assistant. Your task is to determine what kind of data is needed to best respond to the user's message. Choose from the following data types:

    - "poi_data": Information about specific points of interest (e.g., descriptions, opening hours)
    - "poi_location": Data required to help with wayfinding, directions, or location lookup
    - "poi_category": When the user asks for suggestions or recommendations based on categories
    - "weather_data": If the query relates to weather or planning around weather
    - "event_data": If the user asks about local events
    - "none": If the query can be answered using general knowledge without fetching external data

    In addition, if the user's query involves **planning a trip, itinerary, or sequence of visits**, set `"itinerary_planning"` to `true`.

    You should return a JSON object with:
    - "data_required": a list of data types needed (e.g., ["poi_data", "weather_data"])
    - "entities": list of any POIs, categories, or locations mentioned in the query
    - "itinerary_planning": a boolean indicating whether the user is requesting help with planning an itinerary

    Examples:
    {"data_required": ["poi_data"], "entities": ["S.E.A. Aquarium"], "itinerary_planning": false}
    {"data_required": ["poi_category"], "entities": ["museums"], "itinerary_planning": false}
    {"data_required": ["weather_data", "poi_location"], "entities": ["Sentosa Beach"], "itinerary_planning": false}
    {"data_required": ["poi_category", "weather_data"], "entities": ["family attractions", "Sentosa"], "itinerary_planning": true}
    {"data_required": ["none"], "entities": [], "itinerary_planning": false}

    Respond ONLY with the JSON object.
    """
    messages = [
        {"role": "system", "content": prompt},
        {"role": "user", "content": user_input}
    ]
    response = llm.invoke(messages)
    parsed = ast.literal_eval(remove_code_blocks(response))
    print(parsed)
    data_required = parsed["data_required"]
    entities = parsed.get("entities", [])

    # Initialize data bundle
    gathered_data = {}
    if response.get("itinerary_planning") is True:
        # get schema
        schema = load_schema()
        # Generate skeleton
        skeleton = generate_skeleton(llm, schema, user_input)
        # RAG
        pois = rag.query_by_tags(extract_tags_from_trip_schema(schema), top_k=5*get_trip_duration_days(schema))
        # FIll in skeleton
        itinerary = fill_itinerary_skeleton(llm, skeleton, pois, schema)
        # structure itinerary from json.
        pass
    if "poi_data" in data_required:
        gathered_data["poi_data"] = rag.query(entities)

    if "poi_location" in data_required:
        gathered_data["poi_data"] = rag.location_lookup(entities)

    if "poi_category" in data_required:
        category = entities[0] if entities else "general"
        payload = {"page": 1, "size": 50, "category": category}
        pois = call_api(api_url, payload)['data']['content']
        gathered_data["poi_category"] = sample_pois(pois, 3)
    # if "weather_data" in data_required:
    #     gathered_data["weather_data"] = fetch_weather_data(entities)

    # if "event_data" in data_required:
    #     gathered_data["event_data"] = fetch_event_data(entities)

    # Choose appropriate response template
    if "poi_location" in data_required:
        response = nav_intro_prompt(user_input, history, gathered_data).content
        response = hyperlink_pois_in_response(response, gathered_data["poi_data"])
    elif "poi_data" in data_required:
        response = intro_prompt(user_input, history, gathered_data["poi_data"]).content
        response = hyperlink_pois_in_response(response, gathered_data["poi_data"])

    # elif "poi_location" in data_required:
    #     response = wayfind_prompt(user_input, history, gathered_data["poi_data"]).content
    elif "poi_category" in data_required:
        response = rec_prompt(user_input, history, gathered_data["poi_data"]).content 
        response = hyperlink_pois_in_response(response, gathered_data["poi_data"])
    # elif "weather_data" in data_required:
    #     response = weather_prompt(user_input, history, gathered_data["weather_data"]).content
    # elif "event_data" in data_required:
    #     response = event_prompt(user_input, history, gathered_data["event_data"]).content
    else:
        response = basic_prompt(user_input, history).content
    return jsonify({
        "response": response,
        "gatheredData": gathered_data["poi_data"]
    })

@app.route('/find_nearby_pois', methods=['POST'])
def find_nearby_pois():
    try:
        data = request.get_json()
        user_loc = data.get("user_location")
        radius_m = data.get("radius_in_meters", 500)

        if not user_loc or "latitude" not in user_loc or "longitude" not in user_loc:
            return jsonify({"error": "Missing or invalid location"}), 400

        # Convert user location to radians
        user_coords_rad = np.radians([[user_loc["latitude"], user_loc["longitude"]]])
        
        # Radius in radians (Earth's radius ≈ 6,371,000 m)
        radius_rad = radius_m / 6371000.0

        # Query BallTree for nearby POIs
        indices = app.balltree.query_radius(user_coords_rad, r=radius_rad)[0]

        # Get names of nearby POIs
        nearby_poi_names = app.poi_df.iloc[indices]["name"].tolist()

        return jsonify(nearby_poi_names)

    except Exception as e:
        print(f"Error in /find_nearby_pois: {e}")
        return jsonify({"error": "Internal server error"}), 500


############################################ CUSTOMIZATION UI ENDPOINTS #####################################################
@app.route('/bms', methods=["GET"])
def bms_page():
    return render_template("llm-manager.html" , active_tab="llm")

@app.route('/llm_manager', methods=["GET"])
def settings_page():
    return render_template("llm-manager.html", active_tab="llm")

@app.route('/rag_manager', methods=["GET"])
def rag_manager_page():
    return render_template("rag-manager.html", active_tab="rag")

@app.route('/map_manager', methods=["GET"])
def map_manager_page():
    return render_template("map-manager.html", active_tab="map")

@app.route("/api/init_rag", methods=["POST"])
def init_rag():
    global rag_instance
    try:
        if 'csv' in request.files:
            csv_file = request.files['csv']
            # Pass file-like object directly, no need to save to disk
            rag_instance = RAGPlatform(csv_file=csv_file)
            return jsonify(message="CSV loaded successfully")
        elif 'index' in request.files:
            index_file = request.files['index']
            index_file.save("index.faiss")  # Still need to save since loading from file is not implemented
            rag_instance = RAGPlatform(index_file="index.faiss")
            return jsonify(message="Index loaded successfully")
        return jsonify(message="No file provided"), 400
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify(message="Failed to initialize RAG", error=str(e)), 500

@app.route("/api/update_llm", methods=["POST"])
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
        return jsonify(message="LLM pipeline updated successfully")
    except Exception as e:
        return jsonify(error=f"Failed to initialize LLM: {str(e)}"), 500

@app.route("/api/delete_unit", methods=["POST"])
def remove_rag_unit():
    unit_id = request.json['unit_id']
    print(unit_id)
    if unit_id in rag.units:
        rag.remove_unit_by_id(unit_id)

        # === HERE: Update app.poi_df and balltree ===
        app.poi_df = rag.get_all_pois_as_dataframe()
        app.balltree = update_ball_tree(app.poi_df)

        return jsonify({"message": f"RAG Unit {unit_id} removed."}), 200
    return jsonify({"error": f"RAG Unit {unit_id} not found."}), 404


@app.route("/api/add_unit", methods=["POST"])
def add_rag_unit():
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

        return jsonify({"message": f"Unit added with ID {new_unit.id}"}), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/get_units", methods=["GET"])
def get_units():
    units = []
    for unit in rag.units.values():
        units.append({
            "id": unit.id,
            "description": unit.description,
            "source_type": unit.source.get("type", "unknown"),
            "name": unit.name
        })
    return jsonify(units=units)

@app.route('/update_map_style', methods=['POST'])
def update_map_style():
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

############################################ MAP RELATED ENDPOINTS #####################################################
@app.route('/get_coordinates', methods=['POST'])
def get_coordinates():
    places = request.json['places']
    print(places)

    coordinates = []
    found_places = []

    for place in places:
        # Query the MongoDB database directly
        result = rag.query({"name": place.strip()})
        if result:
            lng = float(result["longitude"])
            lat = float(result["latitude"])
            coordinates.append({'lng': lng, 'lat': lat})
            found_places.append(place)

    print(found_places)
    print(coordinates)
    print(len(coordinates))
    return jsonify({"coordinates": coordinates, "places": found_places})

# enpoint to load POI detail. returns name:description pair
@app.route('/place_info', methods=['POST'])
def place_info():
    places = request.json['places']
    print(places)
    output = rag.location_lookup(places)
    print(output)
    return jsonify(output)

@app.route('/calculate_distances', methods=['POST'])
def calculate_distances():
    try:
        # Parse the JSON payload
        data = request.get_json()
        print(data)
        pois = data['pois']
        user_location = data['user_location']
        user_location = [user_location["lng"], user_location["lat"]]
        # Assume a walking speed of 1.39 m/s (5 km/h)
        walking_speed = 0.5  # in meters per second

        # Calculate distances and walking times
        results = {}
        for poi in pois:
            distance = int(get_distance_from_poi(poi, user_location))  # Get the distance
            time = int(distance / walking_speed / 60)  # Calculate time in minutes
            results[poi['name']] = {
                "distance": distance,  # in meters
                "time": time  # in minutes
            }
        print(f"calc distances restults: {results}")
        return jsonify(results)

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/fetch_by_category', methods=['POST'])
def fetch_by_category():
    try:
        data = request.get_json()
        category = data.get('category')

        if not category:
            return jsonify({"error": "No category provided"}), 400

        results = rag.search_by_field("category", category)
        print(results)
        # Compose the place_info dict similar to your original code
        place_info = {}
        for item in results:
            place_name = item.get("name")
            description = item.get("description")
            location = item.get("longitude")
            latitude = item.get("latitude")
            if place_name:
                place_info[place_name] = {
                    "description": description,
                    "longitude": location,
                    "latitude": latitude
                }

        return jsonify(place_info), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500
    
@app.route("/reset_memory")
def reset_memory():
    # Clear memory
    memory.clear()  # Replace with actual memory clearing code
    return jsonify({"status": "Memory reset"})

@app.route("/graph")
def show_graph():
    net = Network(height="600px", width="100%", bgcolor="#222222", font_color="white")

    for _, row in poi_df.iterrows():
        name = row["name"]
        net.add_node(n_id=name, label=name, title=name)

    for u, v, data in graph.edges(data=True):
        weight = data.get("weight", 1)
        net.add_edge(u, v, value=weight, title=f"{weight:.0f}m")

    net.toggle_physics(True)

    # Save to static folder instead of templates
    output_path = os.path.join("templates", "graph.html")
    net.save_graph(output_path)

    # Redirect user to view the static file
    return render_template("graph.html")

@app.route("/graph_map")
def show_graph_map():
    return render_template("graph_map.html", pois=poi_df.to_dict(orient="records"), edges=list(graph.edges()))

############################################# ITINERARY PLANNER ENDPOINTS #####################################################
@app.route('/plan')
def show_form():
    return render_template('itinerary-form.html')

@app.route('/submit_itinerary', methods=['POST'])
def submit_itinerary():
    data = request.form.to_dict()
    data['group_type'] = request.form.getlist('group_type')  # ensure list values are captured

    # Convert checkbox inputs to booleans
    checkbox_fields = ['has_children', 'has_elderly', 'avoid_heat', 'backup_plan']
    for field in checkbox_fields:
        data[field] = field in request.form

    # Save data to user_schema.json
    filepath = './static/data/user_schema.json'
    if os.path.exists(filepath):
        with open(filepath, 'r') as f:
            all_data = json.load(f)
    else:
        all_data = []

    all_data.append(data)

    with open(filepath, 'w') as f:
        json.dump(all_data, f, indent=2)

    return redirect('/')


###########################################################################################################
if __name__ == '__main__':
    app.run(debug=True, host="0.0.0.0", port=3106)
