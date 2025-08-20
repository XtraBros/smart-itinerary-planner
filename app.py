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
from backend.views import backend_bp

app = Flask(__name__)
app.register_blueprint(backend_bp, url_prefix="/admin")

CONFIG_FILE = 'config.json'

with open(CONFIG_FILE, 'r') as file:
    config = json.load(file)

######################### LLM INIT #########################
app.llm = LLMPipeline(provider='openai', model=config['GPT_MODEL'], api_key=config['OPENAI_API_KEY'])
# Initialize memory for conversation
memory = ConversationBufferWindowMemory(k=5, memory_key="history")
######################### RAG Data #########################
unit1 = RAGUnit(
    data_source={"type": "csv", "path": "./zoo-info.csv"},
    description="Zoo info CSV",
    name= "Mandai Zoo CSV"
)
unit2= RAGUnit(
    data_source={"type": "csv", "path": "./sentosa_with_tags.csv"},
    description="Sentosa POI CSV",
    name= "Sentosa Island CSV"
)
app.rag = RAGPlatform([unit2])
balltree, poi_df = build_balltree_from_rag_platform(app.rag)
app.graph = build_graph_from_balltree(poi_df, balltree, np.radians(poi_df[['latitude', 'longitude']].values), k=5)
app.balltree = balltree
app.poi_df = poi_df
poi_df['clicks'] = [random.randint(1, 100) for _ in range(len(poi_df))]

######################### MISC init #########################
api_url = config['API_URL']
locale_name = "Sentosa Island"
# Change place list to poi name list
locale_place_list = poi_df['name'].tolist()

@app.route('/')
def home():
    return render_template('index.html', places=poi_df)

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
    llm = app.llm
    rag = app.rag
    user_input = request.json['message']
    conversation_history = memory.load_memory_variables({})
    history = process_formatted_history(conversation_history.get('history', ''))
    prompt = f"""
    You are a routing agent in a chat-based assistant. Your task is to determine what kind of data is needed to best respond to the user's message. Choose from the following data types:

    - "poi_data": Information about specific points of interest (e.g., descriptions, opening hours)
    - "poi_location": Data required to help with wayfinding, directions, or location lookup
    - "poi_category": When the user asks for suggestions or recommendations based on categories
    - "event_data": If the user asks about local events
    - "none": If the query can be answered using general knowledge without fetching external data

    Additionally, detect if the user's query involves **planning or editing an itinerary**:

    - If the user is **planning a trip or requesting a sequence of visits**, set `"itinerary_planning"` to `true`.
    - If the user wants to **modify an existing itinerary**, set `"itinerary_edit"` to `true`.

    Return a Python dictionary object with:
    - "data_required": a list of data types needed (e.g., ["poi_data", "weather_data"])
    - "entities": list of any POIs, categories, or locations mentioned in the query
    - "itinerary_planning": boolean, true if user is planning an itinerary
    - "itinerary_edit": boolean, true if user wants to edit an itinerary
    - "notes": any additional notes or considerations

    Examples:
    {{"data_required": ["poi_data"], "entities": ["S.E.A. Aquarium"], "itinerary_planning": False, "itinerary_edit": False, "notes": "User is asking for information about a specific POI."}}
    {{"data_required": ["poi_category"], "entities": ["museums"], "itinerary_planning": False, "itinerary_edit": False, "notes": "User is looking for recommendations in a specific category."}}
    {{"data_required": ["poi_data"], "entities": ["Sentosa"], "itinerary_planning": True, "itinerary_edit": False, "notes": "User is planning a trip to Sentosa."}}
    {{"data_required": ["none"], "entities": [], "itinerary_planning": False, "itinerary_edit": True, "notes": "User wants to replace a POI in their existing itinerary."}}

    Respond ONLY with the Python dictionary object.
    """

    messages = [
        {"role": "system", "content": prompt},
        {"role": "user", "content": user_input}
    ]
    response = llm.invoke(messages)
    parsed = ast.literal_eval(remove_code_blocks(response))
    data_required = parsed["data_required"]
    entities = parsed.get("entities", [])

    # Initialize data bundle
    gathered_data = {}
    if parsed.get("itinerary_planning", False) is True:
        schema = load_schema()
        skeleton = generate_skeleton(llm, schema, user_input)
        pois = rag.query_by_tags(extract_rag_tags(schema), attractions_only=True, top_k=8*get_trip_duration_days(schema))
        if parsed["notes"]:
            pois1 = rag.query(parsed["notes"], attractions_only=True)
            pois = pois + pois1
            pois = list({poi["name"]: poi for poi in pois}.values())
        pois_order = solve_route_with_balltree([poi['name'] for poi in pois], app.poi_df, app.balltree)
        pois_order = reorder_and_extract_names(pois, pois_order)
        itinerary = fill_itinerary_skeleton(llm, skeleton, pois, pois_order, schema, user_input)
        response = json_to_itinerary_text(remove_code_blocks(itinerary))
        memory.save_context({"input": user_input}, {"output": response})
        response = hyperlink_pois_in_response(response, pois)
        return jsonify({
            "response": response,
            "gatheredData": sanitize_for_json(pois)
        })
    
    if parsed.get("itinerary_edit", False) is True:
        previous_itinerary = extract_previous_itinerary_from_history(history)
        if not previous_itinerary:
        # Fallback: no itinerary in memory, generate a new one
            schema = load_schema()
            skeleton = generate_skeleton(llm, schema, user_input)
            pois = rag.query_by_tags(extract_rag_tags(schema), attractions_only=True, top_k=8*get_trip_duration_days(schema))
            pois_order = solve_route_with_balltree([poi['name'] for poi in pois], app.poi_df, app.balltree)
            pois_order = reorder_and_extract_names(pois, pois_order)
            itinerary = fill_itinerary_skeleton(llm, skeleton, pois, pois_order, schema, user_input)
            response = json_to_itinerary_text(remove_code_blocks(itinerary))
            response = hyperlink_pois_in_response(response, pois)
            memory.save_context({"input": user_input}, {"output": response})
            return jsonify({
                "response": response,
                "gatheredData": sanitize_for_json(pois)
            })
        else:
            user_input = request.json["message"]      
            matched_pois = rag.get_relevant_pois_from_text_blobs(previous_itinerary, user_input)
            pois = rag.query(matched_pois)
            response = edit_itinerary(user_input, previous_itinerary, pois).content
            response = hyperlink_pois_in_response(response, pois)
            memory.save_context({"input": user_input}, {"output": response})
            return jsonify({
                "response": response,
                "gatheredData": pois  # Optionally include edited data
            })
    
    if "poi_data" in data_required:
        gathered_data["poi_data"] = rag.query(entities)

    # if "poi_location" in data_required:
    #     gathered_data["poi_data"] = rag.location_lookup(entities)

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
    # if "poi_location" in data_required:
    #     response = nav_intro_prompt(user_input, history, gathered_data).content
    #     memory.save_context({"input": user_input}, {"output": response})
    #     response = hyperlink_pois_in_response(response, gathered_data["poi_data"])
    elif "poi_data" in data_required:
        response = intro_prompt(user_input, history, gathered_data["poi_data"]).content
        memory.save_context({"input": user_input}, {"output": response})
        response = hyperlink_pois_in_response(response, gathered_data["poi_data"])

    # elif "poi_location" in data_required:
    #     response = wayfind_prompt(user_input, history, gathered_data["poi_data"]).content
    elif "poi_category" in data_required:
        response = rec_prompt(user_input, history, gathered_data["poi_data"]).content 
        memory.save_context({"input": user_input}, {"output": response})
        response = hyperlink_pois_in_response(response, gathered_data["poi_data"])
    # elif "weather_data" in data_required:
    #     response = weather_prompt(user_input, history, gathered_data["weather_data"]).content
    # elif "event_data" in data_required:
    #     response = event_prompt(user_input, history, gathered_data["event_data"]).content
    else:
        response = basic_prompt(user_input, history).content
        memory.save_context({"input": user_input}, {"output": response})
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



############################################ MAP RELATED ENDPOINTS #####################################################
@app.route('/get_coordinates', methods=['POST'])
def get_coordinates():
    rag = app.rag
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
    rag = app.rag
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
    rag = app.rag
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

@app.route('/api/pois')
def pois():
    df = poi_df[["name", "longitude", "latitude","clicks"]].copy()
    print("Returning POIs data")
    return df.to_dict(orient='records')
############################################# ITINERARY PLANNER ENDPOINTS #####################################################
@app.route('/plan')
def show_form():
    return render_template('itinerary-form.html')

@app.route('/submit_itinerary', methods=['POST'])
def submit_itinerary():
    # Get and clean form data
    form_data = {k: v.strip() if v else "" for k, v in request.form.items()}

    # Ensure the directory exists
    filepath = './data/user_schema.json'
    os.makedirs(os.path.dirname(filepath), exist_ok=True)

    # Overwrite the file with the new form data
    with open(filepath, 'w') as f:
        json.dump(form_data, f, indent=2)

    return redirect('/')
###########################################################################################################
if __name__ == '__main__':
    app.run(debug=True, host="0.0.0.0", port=3106)
