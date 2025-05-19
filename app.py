# app.py

from flask import Flask, render_template, request, jsonify
import pandas as pd
import json
from langchain.memory import ConversationBufferWindowMemory
import ast
from helpers.text_processing import *
from helpers.prompts import *
from helpers.RAG import *
from helpers.model import LLMPipeline
from werkzeug.utils import secure_filename

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
rag = RAGPlatform([unit1])
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

# Existing endpoint
@app.route('/config', methods=['GET'])
def get_config():
    config = load_config()
    return jsonify({'config': config})

# New endpoint to update MAPBOX_STYLE_URL
@app.route('/update_map_style', methods=['POST'])
def update_map_style():
    data = request.json
    new_style_url = data.get("mapbox_style_url")

    if not new_style_url:
        return jsonify({"error": "Missing mapbox_style_url"}), 400

    config = load_config()
    config["MAPBOX_STYLE_URL"] = new_style_url
    save_config(config)

    return jsonify({"message": "Map style URL updated successfully", "style_url": new_style_url})

@app.route('/ops_router', methods=['POST'])
def ops_route():
    user_input = request.json['message']
    # Fetch stored memory (previous conversation history)
    conversation_history = memory.load_memory_variables({})
    # Format the conversation history for the prompt (as a string)
    history = process_formatted_history(conversation_history.get('history', ''))
    print(f"==conv== {history}")
    prompt = f"""
    You are a operations handler. Your task is to understand a query and classify it under one of the following categories: [Wayfinding, POI Introduction, Recommendation, Unclassified].
    Here are some guidelines to determine the classification:
    - Wayfinding: The query involves navigation, how to move from place to palce, or locating a POI.
    - POI Introduction: The query is asking for information or details about a specific POI.
    - Recommendation: The query is asking for recommendations or suggestions.
    - Unclassified: Any query that does not fall into any of the above categories.

    Your response should contain a dictionary with the keys "operation" and "poi". The value for "operation" will be the category the query is classfied as.
    The value for "poi" will be a list of any names of POIs in the user's query. An example response will be: {{"operation": "Wayfinding", "poi":["Miniso"]}}.
    For "operation" Recommendation, your response should have the keys "operation" and "category". Select the most appropriate category from {categories}, and use that as the value for "category".
    An example response for Reommendation is: {{"operation": "Recommendation", "category": "restaurants"}}.
    Your response should contain only one dictionary and nothing else.
    """
    messages = [
        {"role": "system", "content": prompt},
        {"role": "user", "content": user_input}
    ]
    response = llm.invoke(messages)
    message = ast.literal_eval(remove_code_blocks(response.choices[0].message.content))
    # Given the classification, run the subsequent tasks
    # alternatively, use NLP package to classify queries.
    if "poi" in message.keys(): # fetch poi data
        poi_data = rag.query(message['poi'])
    if message['operation'] == "Wayfinding":
        response = wayfind_prompt(user_input,history,poi_data).content
        print(response)
        # return message + poiId to run routing function
        return jsonify({'response' : response, "poiData": poi_data})
    elif message['operation'] == "POI Introduction":
        response = intro_prompt(user_input,history,poi_data).content
        print(response)
        # return message + poiId to run routing function
        return jsonify({'response' : response, "poiData": poi_data})
    elif message['operation'] == "Recommendation":
        # fetch poi by category and randomly select. In future, implement ranking by relevance or vendor
        category = message['category']
        payload = {"page": 1, "size": 50, "category": category}
        pois = call_api(api_url,payload)['data']['content']
        # RAndom sample of 7 pois to recommend
        sample = sample_pois(pois,3)
        print(sample)
        # Return the result as a JSON response
        response = rec_prompt(user_input,history,sample).content
        print(response)
        # return message + poiId to run routing function
        return jsonify({'response' : response, "poiData": sample})
    else:
        # Unclassified or errornous response, simply respond to query with LLM. 
        response = basic_prompt(user_input,history).content
        print(response)
        return jsonify({'response' : response})
    
############################################ CUSTOMIZATION UI ENDPOINTS #####################################################
@app.route('/settings', methods=["GET"])
def settings_page():
    return render_template("customization-page.html")

@app.route('/rag_manager', methods=["GET"])
def rag_manager_page():
    return render_template("rag-manager.html")

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

            # If source is 'index', we still treat the content format as CSV unless further logic is defined
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
        new_unit.build_index()
        rag.add_unit(new_unit)

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
############################################ LEGACY ENDPOINTS #####################################################
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
    output = rag.query(places)
    return jsonify(output)

# Endpoint to fetch events for a given set of POI names, and return a LLM response to inform the user about the events.
# Requires Geospatial database
# @app.route('/check_events', methods=['POST'])
# def check_events():
#     data = request.get_json()  # Get the list of names from the POST request
#     print(f"===check_events==> {data}")
#     places = data.get("places", [])  # Retrieve the 'names' list from the JSON body
#     coordinates = data.get("coordinates", [])
#     promo_blacklist = data.get("blacklist", [])
#     if not places:
#         return jsonify({"error": "No POIs provided"}), 400
#     places =  [place for place in places if place not in promo_blacklist]
#     # Query the database for entries with the given names
#     entries = list(events_db.find({"location": {"$in": places}}))
#     print(f"===check_events results==> {entries}")
#     if entries:
#         found_places = []
#         found_coordinates = []
#         for entry in entries:
#             location = entry['location']
#             if location in places:
#                 index = places.index(location)
#                 found_places.append(location)
#                 found_coordinates.append(coordinates[index])
#         response = client.chat.completions.create(
#             model=model_name,
#             messages=[
#                 {"role": "system", "content": f"""You are an excited event promoter.
#                  Given this list of places: {found_places}, and data regarding the events/promotions happening at these places: {entries}, craft a promotional message to a tourist/visitor to {locale_name}.
#                  Your main task is to introduce the attraction, enticing visitors to visit the attraction with a promotional message. These attractions are determiend to be near the visitor.
#                  The message is addressed to a generic audience, and should be as succint as possible. Leave out any salutations at the end.
#                  Please encase the names of the attractions in "~" symbols (e.g., ~Attraction Name~) to distinguish them. Use the exact names given in the list. """},
#             ],
#             temperature=0,
#         )
#         print(f"===check_events GPT response==> {response}")
#         hyperlinks = create_hyperlinks(places, coordinates)
#         response_text = insertHyperlinks(response.choices[0].message.content.strip(), hyperlinks)
#         memory.save_context({"user_input": ""}, {"response": response.choices[0].message.content.strip()})
#         return jsonify({'response': response_text, "places": found_places, "coordinates": found_coordinates})
#     else:
#         # Return no content if no entries are found
#         return jsonify({}), 204
    
# Fetch POIs by category
@app.route('/fetch_by_category', methods=['POST'])
def fetch_by_category():
    try:
        # Get the category from the incoming JSON request
        data = request.get_json()
        category = data.get('category')

        if not category:
            return jsonify({"error": "No category provided"}), 400
        payload = {"page": 1, "size": 50, "category": category}
        output = call_api(api_url,payload)
        # Return the result as a JSON response
        return jsonify(output.data.content), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500
    
@app.route("/reset_memory")
def reset_memory():
    # Clear memory
    memory.clear()  # Replace with actual memory clearing code
    return jsonify({"status": "Memory reset"})

###########################################################################################################
if __name__ == '__main__':
    app.run(debug=True, host="0.0.0.0", port=3106)
