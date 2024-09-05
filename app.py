# app.py

from flask import Flask, render_template, request, jsonify
from openai import OpenAI
import pandas as pd
import ast
import json
import numpy as np
from thefuzz import fuzz, process
from pymongo import MongoClient
from sentence_transformers import SentenceTransformer
from sklearn.metrics.pairwise import cosine_similarity
from ortools.constraint_solver import pywrapcp, routing_enums_pb2
import requests
from geopy.distance import geodesic
import certifi
import re
import base64
import gridfs


app = Flask(__name__)

CONFIG_FILE = 'config.json'

with open(CONFIG_FILE, 'r') as file:
    config = json.load(file)

client = OpenAI(api_key=config["OPENAI_API_KEY"])
model_name = config['GPT_MODEL']

######################### MONGO #########################
# Connect to MongoDB
mongo_client = MongoClient(config['MONGO_CLUSTER_URI'], tlsCAFile=certifi.where())
db = mongo_client[config['MONGO_DB_NAME']]
poi_db = db[config['POI_DB_NAME']]
# create geosphere index
poi_db.create_index([('location', '2dsphere')])
indexes = poi_db.index_information()
dist_mat = db[config["DISTANCE_MATRIX"]]
thumbnails_db = db["THUMBNAILS"]
fs = gridfs.GridFS(db)
#cluster_loc = db[config['CLUSTER_LOCATIONS']]
# LOAD Vector store into memory if needed. Currently kept in db as column.
# Load the embedding model for semantic search
model = SentenceTransformer('all-MiniLM-L6-v2')
######################### MONGO #########################

######################### CSV DATA #########################
place_info_df = pd.DataFrame(list(poi_db.find({}, {"_id": 0})))
# place_info_df.columns = place_info_df.columns.str.strip()
# place_info_df['name'] = place_info_df['name'].str.strip()
name_to_index = {name: idx for idx, name in enumerate(place_info_df['name'])}
#cluster_locations = pd.DataFrame(list(cluster_loc.find({}, {"_id": 0})))
######################### CSV DATA #########################


zoo_name = "Singapore Zoo"
zoo_places_list = place_info_df['name'].tolist()

sentosa_name = "Singapore Sentosa Island"
sentosa_places_list = place_info_df["name"].tolist()

@app.route('/')
def home():
    return render_template('index.html', places=place_info_df)

@app.route('/config', methods=["GET"])
def get_config():
    return jsonify({'config': config})

# end point to send message to LLM to get POIs
@app.route('/ask_plan', methods=['POST'])
def ask_plan():
    user_input = request.json['message']
    user_location = request.json['userLocation']
    print(request)

    # Initial messages with RAG data
    messages = [
        {"role": "system", "content": f"""You are a helpful tour guide working in {sentosa_name}.
            Your task is to advise visitors on features and attractions in {sentosa_name}.

            Important Guidelines:
            1) Your response **MUST** be structured as a **single** Python dictionary with two keys: "operation" and "response". Do not include any other text or additional keys. You response contain ONLY ONE dictionary.
            2) The "operation" key can only have one of the following values: "message", "location", "route" or "wayfinding".
                - "message": Used when your response does not include locations, and is a direct reply to the user.
                - "location": Used when your response includes locations without providing directions.
                - "route": Used when your response involves providing a route between multiple places of interest.
                - "wayfinding": Used when your response involves providing directions for the user to navigate to a destination.
            3) The "response" key's value depends on the "operation" key:
                - If "operation" is "message", "response" should contain a single string with your text response.
                - If "operation" is "location", "route" or "wayfinding", "response" should contain a list of the names of the places of interest.
            4) Start from the user's location unless the user specifies otherwise. When starting from the user's location, list only the destination(s) in "response".
                - Example: {{"operation":"route","response":["Din Tai Fung"]}} (implies routing from the user's location to Din Tai Fung)
            5) Use the exact names of the places as provided in this list: {sentosa_places_list}.
            6) If the user asks for nearby POIs, use the find_nearby_pois function, and classify as "operation" == "location".

            **Critical Note:** Ensure your response is a valid Python dictionary with the correct "operation" and "response" structure.
        """},
        {"role": "user", "content": user_input}
    ]


    # Handle function calls and get the final response
    state = {
        "called_functions": set(),
        "function_results": {}
    }
    message = handle_function_calls(messages, state)
    print(message)
    # Initialize operation
    operation = 'message'

    try:
        # Parse the message as a Python dictionary
        evaluated_message = json.loads(remove_dupes(message))
        response = evaluated_message['response']
        operation = evaluated_message['operation']
        if isinstance(response, dict):
            # If 'response' is a dictionary, set 'response' and 'operation' to its values
            response = response.get('response', response)
            operation = response.get('operation', operation)
        print(f"'response': {response}, 'operation': {operation}")
        return jsonify({'response': response, 'operation': operation})

    except (ValueError, SyntaxError, json.JSONDecodeError) as e:
        print(f"Error parsing message: {e}")
        # If parsing fails, keep operation as 'message' and return the raw message
        return jsonify({'response': message, 'operation': operation})

# end point to use LLM to structure route as response
@app.route('/get_text', methods=['POST'])
def get_text():
    # Get the 'route' data from the request JSON
    route = request.json['route']
    print(f"route:{route}")
    user_input = request.json['message']
    if isinstance(route[0], list):
        route = route[0]
    try:
        # Continue with your processing
        response = client.chat.completions.create(
            model=model_name,
            messages=[
                {"role": "system", "content": f"""You are a tour guide at {sentosa_name}.
                 Your task is to guide a visitor, introducing them to the attractions they will visit in the sequence given in the following list.
                 Keep your response succinct, engaging, and varied. Avoid repetitive phrases like 'Sure,' and use conversational language that makes the visitor feel welcome.
                 Structure your response as a bulleted list only if there are multiple destinations. Ensure all destinations are covered in you response.
                 If given only one attraction, the user is trying to go from their current location to the specified attraction. A route will be given to them, so let them know the directions have been displayed on their map.
                 Please encase the names of the attractions in `~` symbols (e.g., `~Attraction Name~`) to distinguish them. Use the exact names given in the list."""},
                {"role": "user", "content": f'Suggested route: {str(route)}. User query: {user_input}'}
            ],
            temperature=0,
        )

        # Create hyperlinks with the route names
        hyperlinks = create_hyperlinks(route)

        # Insert hyperlinks using the `~` delimiter
        response_text = insertHyperlinks(response.choices[0].message.content.strip(), hyperlinks)

        return jsonify({'response': response_text})

    except ValueError as ve:
        print(f"ValueError: {ve}")
        return "Error: Malformed data", 400  # Return a meaningful error response

    except Exception as e:
        print(f"Exception: {e}")
        return "Error: Internal Server Error", 500  # Return a generic error response

@app.route('/get_coordinates', methods=['POST'])
def get_coordinates():
    places = request.json['places']
    print(places)

    coordinates = []
    found_places = []

    for place in places:
        # Query the MongoDB database directly
        result = poi_db.find_one({"name": place.strip()}, {"_id": 0, "longitude": 1, "latitude": 1})
        if result:
            lng = float(result["longitude"])
            lat = float(result["latitude"])
            coordinates.append({'lng': lng, 'lat': lat})
            found_places.append(place)

    print(found_places)
    print(coordinates)
    print(len(coordinates))
    return jsonify({"coordinates": coordinates, "places": found_places})

# POST endpoint for optimizing route
@app.route('/optimize_route', methods=['POST'])
def optimize_route():
    try:
        # Parse the incoming JSON request
        data = request.get_json()

        # Extract the list of place names
        place_names = data.get('placeNames')
        print(place_names)

        # Assuming place_names is a list of names to optimize
        ordered_place_indexes = solve_route(place_names)
        print(ordered_place_indexes)

        # Return the optimized route indexes as a JSON response
        return jsonify(ordered_place_indexes)

    except Exception as e:
        # Log the error for debugging purposes
        print(f"Error encountered: {e}")

        # Return a failsafe response indicating a potential network issue
        return jsonify({"message": "It seems my network connection with you is unstable. Please try sending me your message again."}), 500


# enpoint to load POI info from csv file: returns name:description pair
@app.route('/place_info', methods=['POST'])
def place_info():
    places = request.json['places']
    place_info = {}

    for place in places:
        place = place.strip()
        result = poi_db.find_one({"name": place}, {"_id": 0, "name": 1, "description": 1})
        if result:
            place_name = result['name']
            description = result['description']

            # Try different file extensions to find the corresponding thumbnail
            thumbnail_data = None
            filename = f"{re.sub(r'[: ,]+', '-', place_name.lower())}.jpg"
            thumbnail_file = fs.find_one({"filename": filename})
            if thumbnail_file:
                thumbnail_data = base64.b64encode(thumbnail_file.read()).decode('utf-8')

            place_info[place_name] = {
                "description": description,
                "thumbnail": thumbnail_data,
            }

    return jsonify(place_info)

@app.route('/weather_icon', methods=['POST'])
def weather_icon():
    forecast = request.json
    lib = ["Fair", "Fair (Day)", "Fair (Night)", "Fair and Warm", "Partly Cloudy",
        "Partly Cloudy (Day)", "Partly Cloudy (Night)", "Cloudy", "Hazy", "Slightly Hazy",
        "Windy", "Mist", "Fog", "Light Rain", "Moderate Rain", "Heavy Rain", "Passing Showers",
        "Light Showers", "Showers", "Heavy Showers", "Thundery Showers", "Heavy Thundery Showers",
        "Heavy Thundery Showers with Gusty Winds"]
    return jsonify(process.extractOne(forecast,lib)[0])

@app.route('/find_nearby_pois', methods=['POST'])
def find_nearby():
    data = request.get_json()  # Parse the JSON data from the request

    # Extract the required arguments
    user_location = data.get('user_location')
    radius_in_meters = data.get('radius_in_meters')

    if user_location is None or radius_in_meters is None:
        return jsonify({'error': 'Missing required parameters'}), 400

    # Call the find_nearby_pois function with the provided arguments
    nearby_pois = find_nearby_pois(user_location, radius_in_meters)

    # Return the result as JSON
    return jsonify(nearby_pois)

# Temporary endpoint for random suggestion message
@app.route('/suggestion', methods=['POST'])
def suggest():
    import random
    samples = {1:"It’s almost time for lunch, and there is a popular Chinese restaurant, ~Feng Shui Inn~, nearby. Would you like me to direct you there? ",
               2:"There is a popular adventure activity (~iFly Singapore~) near you which is highly rated on Xiaohongshu, would you like to try it out?"}
    sample_pois = {1:"Feng Shui Inn", 2:"iFly Singapore"}
    choice = random.randint(1, 2)
    response = samples[choice]
    poi = sample_pois[choice]
    # Create hyperlinks with the route names
    hyperlinks = create_hyperlinks([poi])

    # Insert hyperlinks using the `~` delimiter
    response_text = insertHyperlinks(response, hyperlinks)
    return jsonify({"message":response_text, "POI": poi})

# Not needed in sentosa variant right now.
# @app.route('/get_centroids', methods=['POST'])
# def get_centroids():
#     names = request.json['names']
#     if not names:
#         return jsonify({'error': 'No names provided'}), 400
#     coords_str = get_unique_clusters_coordinates(names, poi_db, cluster_locations)
#     return jsonify({'centroids': coords_str})

###########################################################################################################
# route optimisation function:
# input: list of place names from CSV.
# output: permutation of indexes based on input e.g. [0,2,3,5,1,4]
def solve_route(place_names):
    # fetch distance matrix
    distance_matrix = pd.DataFrame(list(dist_mat.find({}, {"_id": 0})))
    # remove first column which contains names of locations.
    distance_matrix = distance_matrix.drop(columns=distance_matrix.columns[0])
    # get index of place from csv file
    indices = [name_to_index[name] for name in place_names]
    # Fetch distance matrix subset
    subset_matrix = distance_matrix.iloc[indices, indices]
    # Run TSP pacakge
    permutation = solve_tsp(subset_matrix)
    return permutation

def solve_tsp(distance_matrix):
    # Handle inf values and NA values:
    distance_matrix = distance_matrix.replace([float('inf'), -float('inf')], 1e9)  # Replace inf with a large value
    distance_matrix = distance_matrix.fillna(0)  # Replace NaNs with 0 or an appropriate value
    # Create the routing index manager
    scaled_distance_matrix = (distance_matrix * 1000).round().astype(int)
    manager = pywrapcp.RoutingIndexManager(len(distance_matrix), 1, 0)

    # Create the routing model
    routing = pywrapcp.RoutingModel(manager)

    def distance_callback(from_index, to_index):
        """Returns the distance between the two nodes."""
        # Convert from routing variable Index to distance matrix NodeIndex.
        from_node = manager.IndexToNode(from_index)
        to_node = manager.IndexToNode(to_index)
        return scaled_distance_matrix.iloc[from_node, to_node]

    transit_callback_index = routing.RegisterTransitCallback(distance_callback)

    # Define cost of each arc
    routing.SetArcCostEvaluatorOfAllVehicles(transit_callback_index)

    # Setting first solution heuristic
    search_parameters = pywrapcp.DefaultRoutingSearchParameters()
    search_parameters.first_solution_strategy = (
        routing_enums_pb2.FirstSolutionStrategy.SAVINGS)
    def print_solution(manager, routing, solution):
        """Prints solution on console."""
        print(f"Objective: {solution.ObjectiveValue()/1000} m")
        index = routing.Start(0)
        plan_output = "Route for vehicle 0:\n"
        route_distance = 0
        while not routing.IsEnd(index):
            plan_output += f" {manager.IndexToNode(index)} ->"
            previous_index = index
            index = solution.Value(routing.NextVar(index))
            route_distance += routing.GetArcCostForVehicle(previous_index, index, 0)
        plan_output += f" {manager.IndexToNode(index)}\n"
        plan_output += f"Route distance: {route_distance/1000}m\n"
        print(plan_output)
    # Solve the problem
    solution = routing.SolveWithParameters(search_parameters)
    print_solution(manager,routing,solution)

    # Get the solution and extract the optimal sequence
    if solution:
        index = routing.Start(0)
        optimal_sequence = []
        while not routing.IsEnd(index):
            optimal_sequence.append(manager.IndexToNode(index))
            index = solution.Value(routing.NextVar(index))
        optimal_sequence.append(manager.IndexToNode(index))  # Add the start point to complete the loop
        # sentosa use open routing, use set to remove duplicates.
        return list(set(optimal_sequence))
    else:
        return None
# Function to handle duplicated GPT output
def remove_dupes(response_text):
    # Use a regular expression to find all occurrences of dictionaries
    matches = re.findall(r'\{.*?\}', response_text)

    if matches:
        # Return only the first dictionary
        return matches[0]
    else:
        # If no dictionary is found, return the original response
        return response_text

# Function to create hyperlinks for places
def create_hyperlinks(place_list):
    hyperlinks = {}
    for name in place_list:
        formatted_id = name.replace('"', '').replace(' ', '-').lower()
        # Create the hyperlink HTML
        hyperlink = f'<a href="#" class="location-link" data-marker-id="{formatted_id}">{name}</a>'
        hyperlinks[name] = hyperlink
    return hyperlinks


def insertHyperlinks(message, replacements):
    # Split the message into chunks by the `~` delimiter
    chunks = message.split("~")

    # Map over the chunks to replace matches using a lambda function
    # The lambda function checks if the chunk is in replacements and replaces it, otherwise it returns the chunk unchanged
    chunks = map(lambda chunk: replacements.get(chunk.strip(), chunk), chunks)

    # Reconstruct the message by joining the mapped chunks
    return "".join(chunks)


###########################################################################################################
####################################  FUNCTION CALLING METHODS    #########################################
###########################################################################################################
'''
Functions:
'''
# Your function mappings
def fetch_weather_data():
    url = "https://api.data.gov.sg/v1/environment/24-hour-weather-forecast"
    response = requests.get(url)
    return response.json() if response.status_code == 200 else {"error": "Unable to fetch weather data"}

def fetch_poi_data():
    # Connect to MongoDB and fetch all documents with the required fields, skip descriptions to save tokens
    documents = poi_db.find({}, {"name": 1, "operating_hours": 1})

    poi_data = []

    for doc in documents:
        # Collect the required fields from each document
        poi = {
            "name": doc.get("name", ""),
            "operating_hours": doc.get("operating_hours", ""),
            "description": doc.get("description", "")
        }
        poi_data.append(poi)

    return poi_data

def find_nearby_pois(user_location, radius_in_meters=100):
    user_lon = user_location['longitude']
    user_lat = user_location['latitude']
    print(f"User location in find_nearby_pois: {user_location}")
    try:
        # Convert radius to radians (radius of Earth is approximately 6378100 meters)
        radius_in_radians = radius_in_meters / 6378100.0
        
        # Perform a geospatial query to find POIs directly within the radius
        nearby_pois = poi_db.find({
            "location": {
                "$geoWithin": {
                    "$centerSphere": [[user_lon, user_lat], radius_in_radians]
                }
            }
        }).limit(10)  # Limit results to a maximum of 10 POIs
        
        # Convert the cursor to a list to check what is returned
        nearby_pois_list = list(nearby_pois)
        print(f"Found POIs: {nearby_pois_list}")

        # Extract POI names from the results
        results = [poi['name'] for poi in nearby_pois_list]

        return results

    except Exception as e:
        print(f"Error: {e}")
        return []


'''
Function Mapping: map the function names to the function, so that it can be identified and called in handle_function_calls()
'''
function_mapping = {
    "fetch_weather_data": fetch_weather_data,
    "fetch_poi_data": fetch_poi_data,
    "find_nearby_pois": find_nearby_pois
}
'''
Function Schema:
defines a list of all available functions and their descriptions. GPT will use this schema to decide which
functions are suitable and relevant, and call these functions if needed.
'''
function_schemas = [
    {
        "name": "fetch_weather_data",
        "description": "Fetches the 24-hour weather forecast from data.gov.sg",
        "parameters": {}
    },
    {
    "name": "fetch_poi_data",
    "description": '''Fetches the name, operating hours, and description of all attractions,
                    ammenities, and places of interest in Sentosa from the MongoDB database.
                    Always call this function if recommending attractions or places, or trying to locate a place of interest.''',
    "parameters": {}
    },
    {
        "name": "find_nearby_pois",
        "description": "Finds places of interest (POIs) within a specified radius of the user's location, sorted by proximity.",
        "parameters": {
            "type": "object",
            "properties": {
                "user_location": {
                    "type": "object",
                    "description": "The user's current location.",
                    "properties": {
                        "longitude": {
                            "type": "number",
                            "description": "The longitude of the user's location."
                        },
                        "latitude": {
                            "type": "number",
                            "description": "The latitude of the user's location."
                        }
                    },
                    "required": ["longitude", "latitude"]
                },
                "radius_in_meters": {
                    "type": "number",
                    "description": "The radius within which to find POIs, in meters.",
                    "default": 100
                }
            },
            "required": ["user_location"]
        },
        "responses": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "The name of the place of interest."
                    },
                    "location": {
                        "type": "array",
                        "items": {
                            "type": "number"
                        },
                        "description": "The location of the place of interest as [longitude, latitude]."
                    },
                    "distance": {
                        "type": "number",
                        "description": "The distance from the user's location to the place of interest, in meters."
                    }
                },
                "required": ["name", "location", "distance"]
            }
        }
    }

]

def handle_function_calls(messages, state):
    response = client.chat.completions.create(
        model=model_name,
        messages=messages,
        functions=function_schemas,
        function_call="auto"
    )

    message = response.choices[0].message
    if hasattr(message, 'function_call') and message.function_call:
        function_name = message.function_call.name
        function_args_str = message.function_call.arguments

        # Convert function_args from string to dictionary
        function_args = {}
        if function_args_str:
            function_args = json.loads(function_args_str)

        if function_name not in state["called_functions"]:
            function_to_call = function_mapping.get(function_name)
            if function_to_call:
                try:
                    function_result = function_to_call(**function_args)
                except TypeError as e:
                    function_result = {"error": f"Function call error: {str(e)}"}

                state["called_functions"].add(function_name)
                state["function_results"][function_name] = function_result

                # # Check if the result is from query_expansion and return immediately
                # if function_name == "query_expansion":
                #     return function_result['clarifying_question']

                messages.append({
                    "role": "function",
                    "name": function_name,
                    "content": json.dumps(function_result)  # Ensure content is JSON encoded
                })

                # Recursive call to handle further function calls
                return handle_function_calls(messages, state)
            else:
                messages.append({
                    "role": "function",
                    "name": function_name,
                    "content": json.dumps({"error": "Function not implemented"})
                })
                return handle_function_calls(messages, state)
    else:
        return message.content


###########################################################################################################
if __name__ == '__main__':
    app.run(debug=True, host="0.0.0.0", port=3106)
