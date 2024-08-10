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


app = Flask(__name__)

CONFIG_FILE = 'config.json'

with open(CONFIG_FILE, 'r') as file:
    config = json.load(file)

client = OpenAI(api_key=config["OPENAI_API_KEY"])
model_name = config['GPT_MODEL']

######################### MONGO #########################
# Connect to MongoDB
mongo_client = MongoClient(config['MONGO_CLUSTER_URI'])
db = mongo_client[config['MONGO_DB_NAME']]
poi_db = db[config['POI_DB_NAME']]
dist_mat = db[config["DISTANCE_MATRIX"]]
cluster_loc = db[config['CLUSTER_LOCATIONS']]
collection = db[config['RAG_DB_NAME']]
# LOAD Vector store into memory if needed. Currently kept in db as column.
# Load the embedding model for semantic search
model = SentenceTransformer('all-MiniLM-L6-v2')
######################### MONGO #########################

######################### CSV DATA #########################
place_info_df = pd.DataFrame(list(poi_db.find({}, {"_id": 0})))
place_info_df.columns = place_info_df.columns.str.strip()
place_info_df['name'] = place_info_df['name'].str.strip()
name_to_index = {name: idx for idx, name in enumerate(place_info_df['name'])}
distance_matrix = pd.DataFrame(list(dist_mat.find({}, {"_id": 0})))
# remove first column which contains names of locations.
distance_matrix = distance_matrix.drop(columns=distance_matrix.columns[0])
cluster_locations = pd.DataFrame(list(cluster_loc.find({}, {"_id": 0})))
######################### CSV DATA #########################


zoo_name = "Singapore Zoo"
zoo_places_list = place_info_df['name'].tolist()

sentosa_name = "Singapore Sentosa Island"
sentosa_places_list = "Entrance, Exit, Shangri La, Fort Siloso, SEA Aquarium, Palawan Beach, Tanjong Beach, Sentosa Golf Club, W Singapore, Capella Singapore, Universal Studios Singapore"

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
    
    # Initial messages with RAG data
    messages = [
        {"role": "system", "content": f"""You are a helpful tour guide who is working in {zoo_name}. 
            Your task is to interact with a visitor and advise them on features and attractions in {zoo_name}.
            If you are to suggest attractions at the zoo, follow the following 3 instructions strictly:
            1) Avoid selecting toilets/water points, tram stops, nursing rooms, and shops unless requested. 
            2) Arrange your response as a Python list with the names of the attractions, and reply with ONLY this list and nothing else.
            Otherwise, simply reply to the user's query."""},
        {"role": "user", "content": user_input}
    ]
    # Handle function calls and get the final response
    state = {
        "called_functions": set(),
        "function_results": {}
    }
    message = handle_function_calls(messages, state)
    
    try:
        evaluated_message = ast.literal_eval(message)
        if isinstance(evaluated_message, list):
            operation = 'route'
        else:
            operation = 'message'
    except (ValueError, SyntaxError):
        operation = 'message'
    
    return jsonify({'response': message, 'operation': operation})

# end point to use LLM to structure route as response
@app.route('/get_text', methods=['POST'])
def get_text():
    try:
        # Get the 'route' data from the request JSON
        route = request.json['route']
        user_input = request.json['message']
        # Continue with your processing
        response = client.chat.completions.create(
            model=model_name,
            messages=[
                {"role": "system", "content": f"""You are a tour guide at {zoo_name}. 
                 Your task is to guide a visitor, introducing them the attractions they will visit in the sequence given in the following list.
                 Keep you response succint, and ensure the names of the attractions are encsed in single apostrophies, as given in the list.
                 Structure your response as a bulleted list so that it is easy to read."""},
                {"role": "user", "content": f'Suggested route: {str(route)}. User query: {user_input}'}
            ],
            temperature=0,
        )
        hyperlinks = create_hyperlinks(route)
        response_text = insertHyperlinks(response.choices[0].message.content.strip(), hyperlinks)
        return jsonify({'response':response_text})

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
    places = [place.strip().replace('"', '') for place in places]
    coordinates = []
    for place in places:
        # Find the row in the DataFrame that matches the place name
        row = place_info_df[place_info_df['name'] == place]
        if not row.empty:
            lng = float(row["longitude"].iloc[0])
            lat = float(row["latitude"].iloc[0])
            coordinates.append({'lng': lng, 'lat': lat})
    print(places)
    print(coordinates)
    print(len(coordinates))
    return jsonify(coordinates)

# POST endpoint for optimizing route
@app.route('/optimize_route', methods=['POST'])
def optimize_route():
    data = request.get_json()
    place_names = data.get('placeNames')
    print(place_names)
    place_names = [place.strip().replace('"', '') for place in place_names]
    print(place_names)
    # Assuming place_names is a list of names to optimize
    ordered_place_indexes = solve_route(place_names)
    print(ordered_place_indexes)
    return jsonify(ordered_place_indexes)
    
# enpoint to load POI info from csv file: returns name:description pair
@app.route('/place_info', methods=['POST'])
def place_info():
    places = request.json['places']
    places = [place.strip('[] ').replace("'", "") for place in places]
    # Split the coordinates into separate columns
    filtered_df = place_info_df[place_info_df['name'].isin(places)]
    # Convert the dataframe to a list of dictionaries
    places = filtered_df[['name','description']].set_index('name')['description'].to_dict()
    # return {'name':'description'} 
    #print(places)
    return jsonify(places)

@app.route('/weather_icon', methods=['POST'])
def weather_icon():
    forecast = request.json
    lib = ["Fair", "Fair (Day)", "Fair (Night)", "Fair and Warm", "Partly Cloudy",
        "Partly Cloudy (Day)", "Partly Cloudy (Night)", "Cloudy", "Hazy", "Slightly Hazy",
        "Windy", "Mist", "Fog", "Light Rain", "Moderate Rain", "Heavy Rain", "Passing Showers",
        "Light Showers", "Showers", "Heavy Showers", "Thundery Showers", "Heavy Thundery Showers",
        "Heavy Thundery Showers with Gusty Winds"]
    return jsonify(process.extractOne(forecast,lib)[0])


@app.route('/get_centroids', methods=['POST'])
def get_centroids():
    names = request.json['names']
    if not names:
        return jsonify({'error': 'No names provided'}), 400
    coords_str = get_unique_clusters_coordinates(names, place_info_df, cluster_locations)
    return jsonify({'centroids': coords_str})

###########################################################################################################
# route optimisation function: 
# input: list of place names from CSV. 
# output: permutation of indexes based on input e.g. [0,2,3,5,1,4]
def solve_route(place_names):
    # get index of place from csv file
    indices = [name_to_index[name.replace("'","")] for name in place_names]
    # Fetch distance matrix subset
    subset_matrix = distance_matrix.iloc[indices, indices]
    # Run TSP pacakge
    permutation = solve_tsp(subset_matrix)
    return permutation

def solve_tsp(distance_matrix):
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
        return optimal_sequence
    else:
        return None

# Function to create hyperlinks for places
def create_hyperlinks(place_list):
    hyperlinks = {}
    for name in place_list:
        name = name.replace("'","")
        formatted_id = name.replace(' ', '-').lower()
        # Create the hyperlink HTML
        hyperlink = f'<a href="#" class="location-link" data-marker-id={formatted_id}>{name}</a>'
        hyperlinks[name] = hyperlink
    print(hyperlinks)
    return hyperlinks


def insertHyperlinks(message, replacements):
    # Split the message into chunks by single apostrophes
    chunks = message.split("'")
    
    # Iterate through the chunks and replace matches
    for i in range(len(chunks)):
        chunk = chunks[i].strip()
        if chunk in replacements:
            chunks[i] = replacements[chunk]
            print(chunk)
    
    # Reconstruct the message
    return "'".join(chunks)

# function to get cluster centroid locations
def get_unique_clusters_coordinates(names, df, centroids_df):
    names = [name.replace("'", "") for name in names]
    filtered_df = df[df['name'].isin(names)]
    clusters = filtered_df['cluster']
    centroids = centroids_df[centroids_df['cluster'].isin(clusters)]
    coords_list = centroids.apply(
        lambda row: f"[{row['centroid_longitude']},{row['centroid_latitude']}]", axis=1
    ).tolist()
    print(coords_list)
    return coords_list

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
    # Connect to MongoDB and fetch all documents with the required fields
    documents = poi_db.find({}, {"name": 1, "operating_hours": 1, "description": 1})

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

'''
Function Mapping: map the function names to the function, so that it can be identified and called in handle_function_calls()
'''
function_mapping = {
    "fetch_weather_data": fetch_weather_data,
    "fetch_poi_data": fetch_poi_data
}
'''
Function Schema:
defines a list of all available functions and their descriptions. GPT will use this schema to decide which
functions are suitable and relevant, and call these functions if needed.
'''
function_schemas = [
    {
        "name": "query_expansion",
        "description": "Asks the user for more information to better understand their needs and provide a more personalized experience.",
        "parameters": {
            "type": "object",
            "properties": {
                "context": {
                    "type": "string",
                    "description": "The current conversation context or user input that needs clarification."
                },
                "clarifying_question": {
                    "type": "string",
                    "description": "The question to ask the user to gather more details."
                }
            },
            "required": ["context"]
        }
    },
    {
        "name": "fetch_weather_data",
        "description": "Fetches the 24-hour weather forecast from data.gov.sg",
        "parameters": {}
    },
    {
    "name": "fetch_poi_data",
    "description": "Fetches the name, operating hours, and description of all attractions, ammenities and animals in Singapore Zoo from the MongoDB database.",
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

                messages.append({
                    "role": "function", 
                    "name": function_name, 
                    "content": json.dumps(function_result)  # Ensure content is JSON encoded
                })

                # Recursive call to handle further function calls
                print(state['called_functions'])
                return handle_function_calls(messages, state)
            else:
                messages.append({
                    "role": "function", 
                    "name": function_name, 
                    "content": json.dumps({"error": "Function not implemented"})
                })
                print(state)
                return handle_function_calls(messages, state)
    else:
        return message.content
    
def query_expansion(context, clarifying_question=None):
    # Generate a clarifying question if none is provided
    if not clarifying_question:
        clarifying_question = "Could you provide more details about your preferences or what you're looking for?"

    # Return the question to ask the user
    return {
        "clarifying_question": clarifying_question
    }

def chat_with_gpt(user_query):
    messages = [
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": user_query}
    ]
    state = {
        "called_functions": set(),
        "function_results": {}
    }
    final_response = handle_function_calls(messages, state)
    return final_response

###########################################################################################################
if __name__ == '__main__':
    app.run(debug=True, port=5000)
