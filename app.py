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
events_db = db[config['EVENTS_DB_NAME']]
profile_db = db["PROFILES"]
# create geosphere index
poi_db.create_index([('location', '2dsphere')])
indexes = poi_db.index_information()
dist_mat = db[config["DISTANCE_MATRIX"]]
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
    prompt = f"""
    You are a helpful assistant. Your task is to understand the user's query and suggest attractions in {sentosa_name} based on their needs. The visitor is currently at {user_location}.

    Important Guidelines:
    1) **Response Structure**: Your response **MUST** be a SINGLE Python dictionary with exactly two keys: "operation" and "response". No additional text or keys are allowed. The dictionary should be the only content in your response.
    
    2) **Operation Key**:
    - The "operation" key can only have one of the following values:
        - "location": Use this when your response includes one or more places, locations, or attractions, or when providing directions to a place.
        - "message": Use this when your response is a general reply that does not include any locations or attractions.

    3) **Response Key**:
    - If "operation" is "message", the value of "response" should be a single string containing your text reply.
    - If "operation" is "location", the value of "response" should be a list of the exact names of the places of interest.

    4) **Use Exact POI Names**: Always use the exact names of the places as provided by the {sentosa_places_list} function.

    5) **Finding Nearby POIs**: 
    - If the user asks for nearby places, use the `find_nearby_pois` function with a radius of 200 meters. Set "operation" to "location" if POIs were found. Otherwise, set "operation" to "message" and inform the user that there are no nearby POIs.

    6) **Handling Specific POI Queries**: 
    - If the user asks about a specific place, use the `get_poi_by_name` function to retrieve accurate information about that place.

    7) **User Location Requests**: 
    - If the user asks for their current location, use the `find_nearest_poi` function to locate them based on the nearest point of interest.

    8) **Limiting Results**: 
    - Avoid suggesting toilets and amenities unless the user specifically requests them. Additionally, limit your list of attractions to 5 places unless the user asks for more.

    9) Use the get_user_profile function to determine the user specific considerations. Cater the recommendations towards this user's group dynamics, dietary preferences and racial profile.
    """
    messages = [
        {"role": "system", "content": prompt},
        {"role": "user", "content": user_input}
    ]


    # Handle function calls and get the final response
    state = {
        "called_functions": set(),
        "function_results": {}
    }
    message = remove_code_blocks(handle_function_calls(messages, state))
    print(f"===ask_plan==> {message}")
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
    coordinates = request.json['coordinates']
    print(f"route:{route}")
    user_input = request.json['message']
    prompt = f"""You are a tour guide at {sentosa_name}. 
                Your task is to guide a visitor, introducing them to the attractions they will visit in the sequence given in the following list.
                Keep your response succinct, engaging, and varied. Avoid repetitive phrases like 'Sure,' and use conversational language that makes the visitor feel welcome.
                Structure your response as a numbered list if there are multiple attractions/POIs, and structure it in HTML. Ensure all destinations are covered in your response.
                If given only one attraction, the user is trying to go from their current location to the specified attraction. A route will be given to them, so let them know the directions have been displayed on their map.
                Identify the user's location via the nearest place of interest when required. Do not include any formatting tags like ```html or other code blocks in your response.

                Please encase the names of the attractions in "~" symbols (e.g., ~Attraction Name~) to distinguish them. Use the exact names given in the list.
            """
                
    if route[0]:
        if isinstance(route[0], list):
            route = route[0]
    try:
        # Continue with your processing
        response = client.chat.completions.create(
            model=model_name,
            messages=[
                {"role": "system", "content": prompt},
                {"role": "user", "content": f'Attractions: {str(route)}. User query: {user_input}'}
            ],
            temperature=0,
        )

        # Create hyperlinks with the route names
        hyperlinks = create_hyperlinks(route, coordinates)
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
        print(data)

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
        result = poi_db.find_one({"name": place}, {"_id": 0, "name": 1, "description": 1,"location":1})
        if result:
            place_name = result['name']
            description = result['description']
            location = result['location']
            place_info[place_name] = {
                "description": description,
                "location": location
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
    data = request.get_json()
    choice = int(data.get('choice', 1))

    samples = {
        1: "Lunchtime is just around the corner, and I have some perfect places for you! ~Feng Shui Inn~, is a top-rated Chinese restaurant where you can find all Chinese cuisines. Ready to experience its delicious, authentic flavors? Click and let me guide you there!",
        2: "Hot deals alert! ~The Forum~ is having a flash sale now on luxury products at unbeatable prices, just around the corner. Want to score big on high-end goods for less? Click now, and I will show you the way to massive savings!",
        3: "Hey there! It looks like you've been enjoying your time on Sentosa! 🌞 After all that walking and exploring, how about taking a little break to recharge? ~Baristart Cafe~ is just a short walk away, and it's the perfect spot to sit down, cool off, and grab something refreshing to drink. 🥤 Whether you're craving a cold drink, a quick snack, or just a cozy place to relax, they've got you covered!",
        4: "If you still want to enjoy the outdoors, ~The Palawan Food Trucks~ are just around the corner for you to grab a quick snack and cool beverages to beat the heat!"
        }
    sample_pois = {
        1: "Feng Shui Inn",
        2: "The Forum",
        3: "Baristart Cafe",
        4: "The Palawan Food Trucks"
        }
    if choice not in samples:
        return jsonify({"error": "Invalid choice provided. Please use 1 or 2."}), 400
    response = samples[choice]
    poi = sample_pois[choice]
    coordinate = poi_db.find_one({"name": poi}, {"_id": 0, "longitude": 1, "latitude": 1})
    coord_data = [[coordinate['longitude'],coordinate["latitude"]]]
    # Create hyperlinks with the route names
    hyperlinks = create_hyperlinks([poi], coord_data)

    # Insert hyperlinks using the `~` delimiter
    response_text = insertHyperlinks(response, hyperlinks)
    return jsonify({"message":response_text, "POI": poi})

# Endpoint to fetch events for a given set of POI names, and return a LLM response to inform the user about the events.
@app.route('/check_events', methods=['POST'])
def check_events():
    data = request.get_json()  # Get the list of names from the POST request
    print(f"===check_events==> {data}")
    places = data.get("places", [])  # Retrieve the 'names' list from the JSON body
    coordinates = data.get("coordinates", [])
    if not places:
        return jsonify({"error": "No POIs provided"}), 400

    # Query the database for entries with the given names
    entries = list(events_db.find({"location": {"$in": places}}))
    print(f"===check_events results==> {entries}")
    if entries:
        found_places = []
        found_coordinates = []
        for entry in entries:
            location = entry['location']
            if location in places:
                index = places.index(location)
                found_places.append(location)
                found_coordinates.append(coordinates[index])
        # Craft response message if entries detected.
        response = client.chat.completions.create(
            model=model_name,
            messages=[
                {"role": "system", "content": f"""You are an excited event promoter.
                 Given a list of places, and data regarding the events/promotions happening at these places, craft a promotional message to a tourist/visitor to {sentosa_name}, promoting these POIs and events. 
                 This message is a follow-up response after having introduced some attractions to them. Your main task is to inform them of the promotion.
                 The message is addressed to a generic audience, and should be as succint as possible. Leave out any salutations at the end.
                 If there are multiple promotions, structure you response as a numbered list in HTML.
                 Please encase the names of the attractions in "~" symbols (e.g., ~Attraction Name~) to distinguish them. Use the exact names given in the list. """},
                {"role": "user", "content": f'Places of interest involved: {found_places}. Events data: {entries}.'}
            ],
            temperature=0,
        )
        print(f"===check_events GPT response==> {response}")
        # Create hyperlinks with the route names
        hyperlinks = create_hyperlinks(places, coordinates)
        response_text = insertHyperlinks(response.choices[0].message.content.strip(), hyperlinks)
        return jsonify({'response': response_text, "places": found_places, "coordinates":found_coordinates})
    else:
        # Return no content if no entries are found
        return jsonify({}), 204
    
# Fetch POIs by category
@app.route('/fetch_by_category', methods=['POST'])
def fetch_by_category():
    try:
        # Get the category from the incoming JSON request
        data = request.get_json()
        category = data.get('category')

        if not category:
            return jsonify({"error": "No category provided"}), 400

        # Query MongoDB for entries with matching category, excluding _id
        results = poi_db.find({"category": category}, {"_id": 0, "name": 1, "description": 1, "location": 1})

        # Create a place_info-like structure
        place_info = {}
        for result in results:
            place_name = result['name']
            description = result['description']
            location = result['location']
            place_info[place_name] = {
                "description": description,
                "location": location
            }

        # Return the result as a JSON response
        return jsonify(place_info), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500

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

# handle code chunks and ``` tags 
def remove_code_blocks(content):
    # Use a regular expression to find and remove code blocks starting with ```
    cleaned_content = re.sub(r'```[a-zA-Z]*\n.*?\n```', '', content, flags=re.DOTALL)
    
    # Remove any leftover backticks (``` without a language identifier)
    cleaned_content = re.sub(r'```\n.*?\n```', '', cleaned_content, flags=re.DOTALL)
    
    return cleaned_content.strip()

# Function to create hyperlinks for places
def create_hyperlinks(place_list, coordinates):
    hyperlinks = {}
    for index, name in enumerate(place_list):
        formatted_id = name.replace('"', '').replace(' ', '-').lower()
        # Create a dictionary for coordinates with 'lng' and 'lat' keys
        coord_dict = {"lng": coordinates[index][0], "lat": coordinates[index][1]}
        # Create the hyperlink HTML
        hyperlink = f'<a href="#" class="location-link" data-coordinates="{coord_dict}" data-marker-id="{formatted_id}">{name}</a>'
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

def get_poi_by_name(name):
    # Query the MongoDB collection for the document where the 'name' matches the input
    poi = poi_db.find_one({"name": name}, {"_id": 0})
    
    if poi:
        return poi  # Return the data row/document
    else:
        return None

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

def find_nearest_poi(user_location):
    user_lon = user_location['longitude']
    user_lat = user_location['latitude']
    print(f"User location in find_nearest_poi: {user_location}")
    try:
        # Perform a geospatial query to find the nearest POI
        nearest_poi = poi_db.find_one({
            "location": {
                "$nearSphere": {
                    "$geometry": {
                        "type": "Point",
                        "coordinates": [user_lon, user_lat]
                    },
                    "$maxDistance": 100000  # Optional: Limit to a max distance in meters (100 km in this example)
                }
            }
        })

        if nearest_poi:
            print(f"Found nearest POI: {nearest_poi}")
            return nearest_poi['name']  # Return the name of the nearest POI
        else:
            print("No nearby POIs found.")
            return None

    except Exception as e:
        print(f"Error: {e}")
        return None
    
def get_poi_list():
    return sentosa_places_list

def get_user_profile():
    user_profile = profile_db.find_one({"profile": 0})
    print(user_profile)
    if user_profile:
        return user_profile["description"]
    return "No special considerations"
'''
Function Mapping: map the function names to the function, so that it can be identified and called in handle_function_calls()
'''
function_mapping = {
    "fetch_weather_data": fetch_weather_data,
    "fetch_poi_data": fetch_poi_data,
    "find_nearby_pois": find_nearby_pois,
    "get_poi_by_name": get_poi_by_name,
    "find_nearest_poi": find_nearest_poi,
    "get_user_profile": get_user_profile
    # "get_poi_list":get_poi_list
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
        "name": "get_poi_by_name",
        "description": "Retrieve the data row of a Point of Interest (POI) from the database by its name.",
        "parameters": {
            "type": "object",
            "properties": {
            "name": {
                "type": "string",
                "description": "The name of the POI to search for."
            }
            },
            "required": ["name"]
        }
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
        "description": "Finds places of interest (POIs) within a specified radius of the user's location. Returns an empty list if no POIs were found.",
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
    },
    {
        "name": "find_nearest_poi",
        "description": "Find the nearest point of interest (POI) to the user's location.",
        "parameters": {
            "type": "object",
            "properties": {
            "user_location": {
                "type": "object",
                "description": "The user's current location with latitude and longitude.",
                "properties": {
                "latitude": {
                    "type": "number",
                    "description": "The latitude of the user's location."
                },
                "longitude": {
                    "type": "number",
                    "description": "The longitude of the user's location."
                }
                },
                "required": ["latitude", "longitude"]
            }
            },
            "required": ["user_location"]
        }
    },
    {
        "name": "get_poi_list",
        "description": "Retrieve a list of names for all available POIs (Points of Interest) in Sentosa.",
        "parameters": {}
    },
    {
        "name": "get_user_profile",
        "description": "Fetches the user profile from the database. Includes racial profile, group dynamics and other relevant considerations required to make a recommendation.",
        "parameters": {}
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
    print(f"===message==> {message}")

    if hasattr(message, 'function_call') and message.function_call:
        function_name = message.function_call.name
        print(f"===function call==> {function_name}")
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

                # Check if the result is empty (specific to find_nearby_pois)
                if function_name == "find_nearby_pois" and not function_result:
                    # Generate a custom message for empty result
                    function_result = {"message": "No nearby attractions were found within the specified radius."}

                # Store the function result
                state["called_functions"].add(function_name)
                state["function_results"][function_name] = function_result

                # Append the function result as a message
                messages.append({
                    "role": "function",
                    "name": function_name,
                    "content": json.dumps(function_result)  # Ensure content is JSON encoded
                })

                # Recursive call to handle further function calls
                return handle_function_calls(messages, state)
            else:
                # Handle case when function is not implemented
                messages.append({
                    "role": "function",
                    "name": function_name,
                    "content": json.dumps({"error": "Function not implemented"})
                })
                return handle_function_calls(messages, state)
    else:
        # If no further function call, return the message content
        return message.content


###########################################################################################################
if __name__ == '__main__':
    app.run(debug=True, host="0.0.0.0", port=3106)
