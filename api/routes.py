from flask import Blueprint, request, jsonify, render_template, redirect, current_app
import os, json, ast, numpy as np
from helpers.text_processing import *
from helpers.prompts import *
from helpers.route_solver import *
from helpers.planner import *
from helpers.tasks import TASK_HANDLERS, classify_task
import ast

routes_bp = Blueprint("routes", __name__)

@routes_bp.route('/ops_router', methods=['POST'])
def ops_router():
    data = request.get_json()
    query = data.get("message", "")
    user_location = data.get("user_location", {})
    print(user_location)
    if not query:
        return jsonify({"error": "Query is required"}), 400

    # Step 1: classify
    task_type, spatial_type = classify_task(query)
    print(f"=========> Ops Router Classification: {task_type, spatial_type}")
    # Step 2: route to handler
    handler = TASK_HANDLERS.get(task_type)
    if not handler:
        return jsonify({"error": f"No handler found for task {task_type}"}), 500

    # Step 3: execute and get results
    result = handler(current_app, query, user_location, spatial_type)
    response_text = result.get('response', '')
    poi_data = result.get('poi_data', [])
    # Step 4: Post-processing to insert links and other features
    response, poi_data = clean_and_filter_response(hyperlink_pois_in_response(response_text, poi_data), poi_data)
    if len(poi_data) < 1:
        task_type = "generic"  # reset to generic if no poi data found
    # print({"response": response, "poiData": poi_data})
    current_app.memory.save_context({"input": query}, {"output": response})
    return jsonify({"response": response, "poiData": poi_data, "task": task_type}), 200


@routes_bp.route('/find_nearby_pois', methods=['POST'])
def find_nearby_pois():
    try:
        data = request.get_json()
        user_loc = data.get("user_location")
        radius_m = data.get("radius_in_meters", 500)

        if not user_loc or "latitude" not in user_loc or "longitude" not in user_loc:
            return jsonify({"error": "Missing or invalid location"}), 400

        # Access the global RAGPlatform instance
        rag_platform = current_app.rag 

        if not rag_platform.balltree or rag_platform.balltree_df is None:
            return jsonify({"error": "BallTree not built. Please rebuild the index."}), 500

        # Convert user coordinates into radians
        user_coords_rad = np.radians([[user_loc["latitude"], user_loc["longitude"]]])
        radius_rad = radius_m / 6371000.0  # meters -> radians on Earth sphere

        # Query the BallTree
        indices = rag_platform.balltree.query_radius(user_coords_rad, r=radius_rad)[0]

        # Get full POI rows
        nearby_pois = rag_platform.balltree_df.iloc[indices]
        nearby_pois = nearby_pois.where(pd.notnull(nearby_pois), None)
        # Turn into JSON-safe objects (dicts)
        pois_serializable = nearby_pois.to_dict(orient="records")

        return jsonify(pois_serializable), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@routes_bp.route('/get_coordinates', methods=['POST'])
def get_coordinates():
    rag = current_app.rag
    places = request.json['places']

    coordinates, found_places = [], []
    for place in places:
        result = rag.query({"name": place.strip()})
        if result:
            lng, lat = float(result["longitude"]), float(result["latitude"])
            coordinates.append({'lng': lng, 'lat': lat})
            found_places.append(place)

    return jsonify({"coordinates": coordinates, "places": found_places})


@routes_bp.route('/place_info', methods=['POST'])
def place_info():
    rag = current_app.rag
    places = request.json['places']
    poi_data = rag.get_poi_details(places)
    response = {}
    for i in poi_data:
        response[i["name"]] = {
            "description": i['description'],
            "location": [i['longitude'],i['latitude']]
        }
    print(response)
    return jsonify(response)


@routes_bp.route('/calculate_distances', methods=['POST'])
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
            poi_location = current_app.rag.get_coordinates(poi['name'])
            distance = int(get_distance_from_poi(poi_location, user_location))  # Get the distance
            time = int(distance / walking_speed / 60)  # Calculate time in minutes
            results[poi['name']] = {
                "distance": distance,  # in meters
                "time": time  # in minutes
            }
        print(f"calc distances restults: {results}")
        return jsonify(results)

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@routes_bp.route('/fetch_by_category', methods=['POST'])
def fetch_by_category():
    try:
        rag = current_app.rag
        category = request.get_json().get('category')

        if not category:
            return jsonify({"error": "No category provided"}), 400

        results = rag.filter_by_category(category)
        print(results.columns)
        place_info = {
            row["name"]: {
                "description": row.get("description", ""),
                "longitude": row.get("longitude"),
                "latitude": row.get("latitude"),
            }
            for _, row in results.iterrows()
            if row.get("name")
        }
        print(place_info)
        return jsonify(place_info)

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@routes_bp.route("/get_bounds")
def get_bounds():
    try:
        rag = current_app.rag
        bounds = rag.get_bounds_from_balltree()
        center_lon = (bounds[0][0] + bounds[1][0]) / 2
        center_lat = (bounds[0][1] + bounds[1][1]) / 2
        print(f"Bounds: {bounds}, Center: {[center_lon, center_lat]}")
        return jsonify({"bounds": bounds, "center": [center_lon, center_lat]})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@routes_bp.route("/reset_memory")
def reset_memory():
    current_app.memory.clear()
    return jsonify({"status": "Memory reset"})


@routes_bp.route('/api/pois')
def pois():
    df = current_app.poi_df[["name", "longitude", "latitude"]].copy()
    df['clicks'] = [random.randint(1, 100) for _ in range(len(df))]

    return df.to_dict(orient='records')


@routes_bp.route('/plan')
def show_form():
    return render_template('itinerary-form.html')


@routes_bp.route('/submit_itinerary', methods=['POST'])
def submit_itinerary():
    form_data = {k: v.strip() if v else "" for k, v in request.form.items()}
    filepath = './data/user_schema.json'
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    with open(filepath, 'w') as f:
        json.dump(form_data, f, indent=2)
    return redirect('/')


####################################################### Helpers #######################################################

def fetch_required_data(rag, df, routing_info: dict) -> dict:
    gathered = {"poi_data": [], "poi_location": [], "poi_category": [], "event_data": []}
    entities = routing_info.get("entities", [])

    if "poi_data" in routing_info["data_required"]:
        gathered["poi_data"].extend(rag.query(entities))

    if "poi_category" in routing_info["data_required"]:
        valid_entities = [e for e in entities if e.lower() in map(str.lower, df['category'].unique())]
        gathered["poi_data"].extend(rag.search_by_category(valid_entities))

    # placeholder for future expansion (events, weather, etc.)
    return gathered

def handle_itinerary_planning(app, rag, llm, memory, user_input, routing_info):
    pois = rag.query(routing_info.get("entities", []))
    response = plan_itinerary(app, rag, llm, user_input, routing_info, memory)
    response = hyperlink_pois_in_response(response, pois)
    memory.save_context({"input": user_input}, {"output": response})
    return jsonify({"response": response, "gatheredData": sanitize_for_json(pois)})


def handle_itinerary_edit(app, rag, llm, memory, user_input, routing_info):
    conversation_history = memory.load_memory_variables({})
    history = process_formatted_history(conversation_history.get('history', ''))
    previous_itinerary = extract_previous_itinerary_from_history(history)

    if not previous_itinerary:
        return handle_itinerary_planning(app, rag, llm, memory, user_input, routing_info)

    matched_pois = rag.get_relevant_pois_from_text_blobs(previous_itinerary, user_input)
    pois = rag.query(matched_pois)
    response = edit_itinerary(user_input, previous_itinerary, pois).content
    response = hyperlink_pois_in_response(response, pois)
    memory.save_context({"input": user_input}, {"output": response})
    return jsonify({"response": response, "gatheredData": pois})
