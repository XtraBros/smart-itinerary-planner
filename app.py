# app.py

from flask import Flask, render_template, request, jsonify
from openai import OpenAI
import pandas as pd
import ast
import json
from config import OPENAI_API_KEY
import numpy as np
from thefuzz import fuzz, process
from pymongo import MongoClient
from sentence_transformers import SentenceTransformer
from sklearn.metrics.pairwise import cosine_similarity

app = Flask(__name__)

client = OpenAI(api_key=OPENAI_API_KEY)
model_name = "gpt-4"

######################### MONGO #########################
# Connect to MongoDB
mongo_client = MongoClient('localhost', 27017)
db = mongo_client['file_db']
collection = db['files']
# LOAD Vector store into memory if needed. Currently kept in db as column.
# Load the embedding model for semantic search
model = SentenceTransformer('all-MiniLM-L6-v2')
######################### MONGO #########################

# Load data once when the server starts
place_info_df = pd.read_csv('zoo-info.csv')
place_info_df.columns = place_info_df.columns.str.strip()
place_info_df['name'] = place_info_df['name'].str.strip()
place_info_df['coordinate'] = place_info_df['coordinate'].str.strip().str.replace('(', '').str.replace(')', '')

zoo_name = "Singapore Zoo"
zoo_places_list = place_info_df['name'].tolist()

sentosa_name = "Singapore Sentosa Island"
sentosa_places_list = "Entrance, Exit, Shangri La, Fort Siloso, SEA Aquarium, Palawan Beach, Tanjong Beach, Sentosa Golf Club, W Singapore, Capella Singapore, Universal Studios Singapore"

@app.route('/')
def home():
    return render_template('index.html', places=place_info_df)

# end point to send message to LLM to get POIs
@app.route('/ask_plan', methods=['POST'])
def ask_plan():
    user_input = request.json['message']
    # Perform RAG instead of fuzzy search:
    # Vectorise message and search vector store to find matching document descriptions
    file_matches = search_files(user_input, top_k=3)
    print(file_matches)
    filenames = [result[0] for result in file_matches]
    data = retrieve_files(filenames)
    print(data)
    # Generate prompt and prompt LLM
    response = client.chat.completions.create(
        model=model_name,
        messages=[
            {"role": "system", 
             "content": f"""You are a helpful tour guide who is working in {zoo_name}. Your task is to answer visitors' questions about how to plan their trip in this place.
             If not specified, the visitors will start from at the Entrance/Exit by default. 
             Avoid mentioning toilets/water points, tram stops, nursing rooms and shops unless requested. Ensure the names of attractions are encased in single apostrophies.
             Here is some data to help you answer the query: [{str(data)}]"""},
            {"role": "user", "content": user_input}
        ],
        temperature=0,
    )
    response_text = response.choices[0].message.content.strip()   
    # Change get_route to return None if no route is available, and bypass hyperlink isnertion
    route = get_route(response_text)
    if len(ast.literal_eval(route)) > 1:
        hyperlinks = create_hyperlinks(ast.literal_eval(route))
        response_text = insertHyperlinks(response_text,hyperlinks)
    return jsonify({'response': [response_text,route]}) 

# end point to use LLM to structure route as response
#@app.route('/get_route', methods=['POST'])
def get_route(user_input):
    #user_input = request.json['message']
    response = client.chat.completions.create(
        model=model_name,
        # update content to be given a route, and explain GPT step by step.
        messages=[
            {"role": "system", "content": f"""You are given a trip plan of this place: {zoo_name}. 
             Your task is to analyze the plan and output a list of names of all attractions/amenities into a pair of brackets, 
             and separate them by commas. You must only list the names that exist in the given list: [{zoo_places_list}]. 
             They should also be in the same order as they appear in the trip plan. Here is an example resulting list: 
             [Entrance, Place A, Place B, Place C, Exit]. In the event no clear plan is given, 
             simply create a list of the attractions in the order they are mentioned. If no attractions are detected, return an empty list."""},
            {"role": "user", "content": user_input}
        ],
        temperature=0,
    )
    return response.choices[0].message.content.strip()

@app.route('/get_coordinates', methods=['POST'])
def get_coordinates():
    places = request.json['places']
    places = [place.strip('[] ').replace("'", "") for place in places]
    print("places: ", places)
    coordinates = []
    for place in places:
        # Find the row in the DataFrame that matches the place name
        row = place_info_df[place_info_df['name'] == place]
        if not row.empty:
            coord = row['coordinate'].values[0]
            lng, lat = map(float, coord.split(';'))
            coordinates.append({'lng': lng, 'lat': lat})
    print("coordinates: ", coordinates)
    return jsonify(coordinates)

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


###########################################################################################################
# No end point functions
def fuzzyMatch(message, choices):
    matches = process.extract(message,choices)
    print(matches)
    result = [t[0] for t in matches if t[1] >= 60]
    print(result)
    if len(result) > 0:
        return result
    else:
        return None
# Function to create hyperlinks for places
def create_hyperlinks(place_list):
    hyperlinks = {}
    for name in place_list:
        formatted_id = name.replace(' ', '-').lower()
        # Create the hyperlink HTML
        hyperlink = f'<a href="#" class="location-link" data-marker-id={formatted_id}>{name}</a>'
        hyperlinks[name] = hyperlink
    return hyperlinks


def insertHyperlinks(message, replacements):
    # Split the message into chunks by single apostrophes
    chunks = message.split("'")
    
    # Iterate through the chunks and replace matches
    for i in range(len(chunks)):
        chunk = chunks[i].strip()
        if chunk in replacements:
            chunks[i] = replacements[chunk]
    
    # Reconstruct the message
    return "'".join(chunks)

# Function to perform vector search
def search_files(query, top_k=5):
    query_vector = model.encode(query).reshape(1, -1)

    # Fetch all documents from the collection
    all_documents = list(collection.find({}, {"file_name": 1, "description": 1, "vector": 1}))
    
    # Calculate cosine similarity
    results = []
    for doc in all_documents:
        doc_vector = np.array(doc["vector"]).reshape(1, -1)
        similarity = cosine_similarity(query_vector, doc_vector)[0][0]
        results.append((doc["file_name"], doc["description"], similarity))
    
    # Sort results by similarity
    results.sort(key=lambda x: x[2], reverse=True)
    return results[:top_k]

def retrieve_files(file_names):
    documents = collection.find({"file_name": {"$in": file_names}})
    retrieved_files = {}
    
    for doc in documents:
        file_content = doc.get("content", {})
        file_name = doc.get("file_name", "")
        # Convert file content to a readable format for LLM
        if isinstance(file_content, list):
            content_str = json.dumps(file_content, indent=2)
        elif isinstance(file_content, dict):
            content_str = json.dumps(file_content, indent=2)
        else:
            content_str = str(file_content)
        retrieved_files[file_name] = content_str
    
    return retrieved_files

###########################################################################################################
if __name__ == '__main__':
    app.run(debug=True, port=5000)
