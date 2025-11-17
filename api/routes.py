from flask import Blueprint, request, jsonify, render_template, redirect, current_app, Response, stream_with_context
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

    if not query:
        return jsonify({"error": "Query is required"}), 400

    task_type, spatial_type = classify_task(query)
    handler = TASK_HANDLERS.get(task_type)
    print(f"=========> Ops Router Classification: {task_type, spatial_type}")

    if not handler:
        return jsonify({"error": f"No handler for {task_type}"}), 500

    def stream():
        full_poi_data = []
        out_data = []
        buffer = ""  # <- accumulated raw text chunks until a full sentence is ready

        try:
            for event in handler(current_app, query, user_location, spatial_type):
                if event.get("type") == "poi_data":
                    full_poi_data.extend(event.get("content", []))
                    continue

                if event.get("type") == "content":
                    raw = event["content"]
                    buffer += raw  # <-- accumulate partial tokens

                    # Detect if we have at least one full sentence or paragraph
                    # End of sentence markers
                    sentence_endings = [".", "?", "!", "。", "！", "？"]

                    # If buffer contains a sentence
                    if any(end in buffer for end in sentence_endings):
                        # Split into sentences
                        import re
                        sentences = re.split(r'(?<=[.!?])\s+', buffer)

                        # Keep the last partial sentence in buffer
                        buffer = sentences.pop()  

                        # Process all complete sentences and stream them
                        for sentence in sentences:
                            final_text, filtered = clean_and_filter_response(
                                hyperlink_pois_in_response(sentence, full_poi_data),
                                full_poi_data
                            )

                            yield json.dumps(
                                {"type": "content", "content": final_text},
                                ensure_ascii=False
                            ) + "\n"
                            out_data.extend(filtered)

            # After handler finishes:
            # If leftover buffer contains any residual text, process it too
            if buffer.strip():
                final_text, _ = clean_and_filter_response(
                    hyperlink_pois_in_response(buffer, full_poi_data),
                    full_poi_data
                )
                yield json.dumps(
                    {"type": "content", "content": final_text},
                    ensure_ascii=False
                ) + "\n"

            # Emit POI data
            yield json.dumps(
                {"type": "poi_data", "content": out_data},
                ensure_ascii=False
            ) + "\n"

            yield json.dumps(
                {"type": "done", "task": task_type},
                ensure_ascii=False
            ) + "\n"

        except Exception as e:
            yield json.dumps({"type": "error", "error": str(e)}, ensure_ascii=False) + "\n"

    return Response(stream_with_context(stream()), mimetype="application/json")



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
