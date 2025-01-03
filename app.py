# app.py

from flask import Flask, render_template, request, jsonify
from openai import OpenAI
import pandas as pd
import json
from pymongo import MongoClient
from sentence_transformers import SentenceTransformer
# from thefuzz import process
import requests
from langchain.memory import ConversationBufferWindowMemory
from langchain.prompts import PromptTemplate
from langchain.schema import HumanMessage, AIMessage
import certifi
import re
from concurrent.futures import ThreadPoolExecutor
from helpers.text_processing import *
from api.data_apis import *

app = Flask(__name__)

CONFIG_FILE = 'config.json'

with open(CONFIG_FILE, 'r') as file:
    config = json.load(file)

######################### LLM INIT #########################
client = OpenAI(api_key=config["OPENAI_API_KEY"])
model_name = config['GPT_MODEL']
# Initialize memory for conversation
memory = ConversationBufferWindowMemory(k=3, memory_key="history")
######################### MongoDB #########################
# Connect to MongoDB
mongo_client = MongoClient(config['MONGO_CLUSTER_URI'], tlsCAFile=certifi.where())
db = mongo_client[config['MONGO_DB_NAME']]
poi_db = db[config['POI_DB_NAME']]
events_db = db[config['EVENTS_DB_NAME']]
profile_db = db["PROFILES"]
######################### CSV DATA #########################
# Load POI List from csv file:
place_info = pd.read_csv("./jewel.csv")
# Table columns: [floor, floorId, icon, location, name, poiId, unit]
place_info_df = pd.DataFrame(place_info)
######################### MISC init #########################
api_url = config['API_URL']

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
    
    # Fetch stored memory (previous conversation history)
    conversation_history = memory.load_memory_variables({})
    # Format the conversation history for the prompt (as a string)
    formatted_history = process_formatted_history(conversation_history.get('history', ''))
    print(f"==conv== {formatted_history}")

    # Prompt template with memory integration
    prompt_template = PromptTemplate(
        input_variables=["history", "user_location", "sentosa_places_list"],
        template="""
        You are a helpful assistant tasked with understanding the user's query and suggesting attractions in Sentosa Island based on their needs. The visitor is currently at {user_location}.

        Guidelines:
        1) **Response Format**: Respond with a Python dictionary containing exactly two keys: "operation" and "response". Only this dictionary should be in the response, with no extra text or keys.

        2) **Operation Key**:
        - "operation" can only be "location" or "message".
        - Use "location" when referring to places or providing directions, and "message" for general responses.

        3) **Response Key**:
        - If "operation" is "message", set "response" as a text string.
        - If "operation" is "location", set "response" as a list of exact place names.

        4) **Exact POI Names**: Use only names from {sentosa_places_list}. If a place is not on this list, use the nearest match.

        5) **Nearby Places**: 
        - For nearby locations, use `find_nearby_pois` with a 200-meter radius. Set "operation" to "location" if POIs are found; otherwise, use "message" to inform the user of no nearby POIs.

        6) **Specific POI Info**: 
        - For details about a specific POI, use `get_poi_by_name` to get the data and reply with operation "message".
        - For Sensoryscape queries, list the 8 "Sensoryscape:..." attractions first (operation "location"); if more info is needed, introduce "Sentosa Sensoryscape" using "get_poi_by_name" with "operation" as "message".

        7) **Location Requests**: 
        - For current location, use `find_nearest_poi` with operation "location."
        - For directions to a POI, use operation "location" and include the POI name. If no POI is specified, refer to the last mentioned POI in conversation history without confirmation. Avoid function calls for directions.

        8) **Result Limits**: 
        - Only suggest amenities if requested, and limit to 3 attractions unless the user specifies otherwise.

        9) **Personalized Recommendations**: Always use `get_user_profile` to tailor suggestions to the user's group dynamics, dietary needs, and preferences.

        Conversation history:
        {history}
        """
    )

    # Create the prompt by filling in values including memory (conversation history)
    prompt = prompt_template.format(
        history=formatted_history,  # Inject conversation history
        user_location=user_location,
        sentosa_places_list=sentosa_places_list
    )

    messages = [
        {"role": "system", "content": prompt},
        {"role": "user", "content": user_input}
    ]

    # Handle function calls and get the final response
    state = {
        "called_functions": set(),
        "function_results": {}
    }
    
    # Process the messages
    message = remove_code_blocks(handle_function_calls(messages, state))
    
    # Update memory with new user input and assistant response
    memory.save_context(
        {"user_input": user_input},  # New user input
        {"message": message}  # Assistant response
    )
    
    print(f"===ask_plan==> {message}")

    # Initialize operation
    operation = 'message'

    try:
        # Parse the message as a Python dictionary
        evaluated_message = json.loads(remove_dupes(message))
        response = evaluated_message['response']
        response = url_to_hyperlink(response)
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
    print(f"=== get_text ===> {route}")
    user_input = request.json['message']
    conversation_history = memory.load_memory_variables({})
    # Format the conversation history for the prompt (as a string)
    formatted_history = process_formatted_history(conversation_history.get('history', ''))
    prompt_template = PromptTemplate(
        input_variables=["history", "route"],
        template = """You are a tour guide at Sentosa. The attractions/destinations you need you cover in your response are {route}.
                    Your task is to guide a visitor, introducing them to the attractions they will visit in the sequence given in the following list.
                    Keep your response succinct, engaging, and varied. Avoid repetitive phrases like 'Sure,' or "Welcome to ..." and use conversational language that makes the visitor feel welcome.
                    Structure your response as a numbered list if there are multiple attractions/POIs. Ensure all destinations are covered in your response.
                    For wayfinding to POIs, the location will be displayed on the user's map, so just inform them so. 
                    Identify the user's location via the nearest place of interest when required. Do not include any formatting tags like ```html and escape sequences like \n in your response.

                    Please encase the names of the attractions in "~" symbols (e.g., ~Attraction Name~) to distinguish them. Use the exact names given in the list.
                    Conversation history:
                    {history}
                """
    )
    prompt = prompt_template.format(
        history=formatted_history,  # Inject conversation history
        route=route
    )
                
    if route[0]:
        if isinstance(route[0], list):
            route = route[0]
    try:
        # Continue with your processing
        response = client.chat.completions.create(
            model=model_name,
            messages=[
                {"role": "system", "content": prompt},
                {"role": "user", "content": user_input}
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

# enpoint to load POI detail. returns name:description pair
@app.route('/place_info', methods=['POST'])
def place_info():
    places = request.json['places']
    place_info = {}
    # Fetch the uids from the DataFrame
    uids = place_info_df[place_info_df['name'].isin(places)]['poiId'].tolist()
    # Use ThreadPoolExecutor to map the API call over the list of uids
    with ThreadPoolExecutor() as executor:
        results = list(executor.map(get_poi_description, uids))

    # Combine the uids with their respective API call results
    output = [{"uid": uid, "data": result} for uid, result in zip(uids, results)]
    return jsonify(output)


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
    promo_blacklist = data.get("blacklist", [])
    if not places:
        return jsonify({"error": "No POIs provided"}), 400
    places =  [place for place in places if place not in promo_blacklist]
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
        response = client.chat.completions.create(
            model=model_name,
            messages=[
                {"role": "system", "content": f"""You are an excited event promoter.
                 Given this list of places: {found_places}, and data regarding the events/promotions happening at these places: {entries}, craft a promotional message to a tourist/visitor to {sentosa_name}.
                 Your main task is to introduce the attraction, enticing visitors to visit the attraction with a promotional message. These attractions are determiend to be near the visitor.
                 The message is addressed to a generic audience, and should be as succint as possible. Leave out any salutations at the end.
                 Please encase the names of the attractions in "~" symbols (e.g., ~Attraction Name~) to distinguish them. Use the exact names given in the list. """},
            ],
            temperature=0,
        )
        print(f"===check_events GPT response==> {response}")
        hyperlinks = create_hyperlinks(places, coordinates)
        response_text = insertHyperlinks(response.choices[0].message.content.strip(), hyperlinks)
        memory.save_context({"user_input": ""}, {"response": response.choices[0].message.content.strip()})
        return jsonify({'response': response_text, "places": found_places, "coordinates": found_coordinates})
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
    print(poi)
    
    if poi:
        return poi  # Return the data row/document
    else:
        return None

def find_nearby_pois(user_location, radius_in_meters=100):
    user_lon = user_location['longitude']
    user_lat = user_location['latitude']
    print(f"User location in find_nearby_pois: {user_location}")
    try:
        # Perform a geospatial query using $geoNear
        nearby_pois = poi_db.aggregate([
            {
                "$geoNear": {
                    "near": {"type": "Point", "coordinates": [user_lon, user_lat]},
                    "distanceField": "distance",
                    "spherical": True,
                    "maxDistance": radius_in_meters
                  }
            },
            {"$limit": 10}  # Limit results to a maximum of 10 POIs
        ])

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
    "get_user_profile": get_user_profile,
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
    },
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
            print("===content is None, generating final response===")
            return generate_final_gpt_response(messages, state)
    else:
        # If no further function call and message content is None
        if message.content is None:
            print("===content is None, generating final response===")
            return generate_final_gpt_response(messages, state)
        else:
            # If message.content exists, return the message content
            print(f"=== function call response === {message.content}")
            return message.content


def generate_final_gpt_response(messages, state):
    """
    This function sends the original query along with the function results back to GPT
    to generate a final response based on both.
    """
    # Construct a message to pass the function results back to GPT
    original_query = messages[1]["content"]
    print(f"== original query == {original_query}")
    # Prepare the function results summary
    function_results_summary = ""
    for function_name, result in state["function_results"].items():
        function_results_summary += f"Result from {function_name}: {json.dumps(result)}\n"
    print(f"== Function calling results in final resp == {function_results_summary}")
    # Add a message to provide context to GPT
    final_messages = [
        {"role": "system", "content": f'''Generate a response to answer the user's query using the following function call results.
         Important Guidelines:
        1) **Response Structure**: Your response **MUST** be a SINGLE Python dictionary with exactly two keys: "operation" and "response". No additional text or keys are allowed. The dictionary should be the only content in your response.

        2) **Operation Key**:
        - The "operation" key can only have one of the following values:
            - "location": Use this when your response includes any place, location, attraction, or when providing directions.
            - "message": Use this when your response is a general reply that does not include any locations or attractions.

        3) **Response Key**:
        - If "operation" is "message", the value of "response" should be a single string containing your text reply.
        - If "operation" is "location", the value of "response" should be a list of the exact names of the places of interest.

        4) **Use Exact POI Names**: Always use the exact names of the places as provided in {sentosa_places_list}.
        
        5) Your response should mainly address the user.
         '''},
        {"role": "user", "content": original_query},
        {"role": "system", "content": f"Function call results:\n{function_results_summary}"}
    ]

    # Call GPT to generate a final response
    final_response = client.chat.completions.create(
        model=model_name,
        messages=final_messages
    )
    print(f"==final resp== {final_response.choices[0].message.content}")
    # Return the final response from GPT
    return final_response.choices[0].message.content

###########################################################################################################
if __name__ == '__main__':
    app.run(debug=True, host="0.0.0.0", port=3106)
