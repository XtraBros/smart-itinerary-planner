# app.py

from flask import Flask, render_template, request, jsonify
from openai import OpenAI
import pandas as pd
import ast
from thefuzz import fuzz, process
from config import OPENAI_API_KEY
import re
import json

app = Flask(__name__)

client = OpenAI(api_key=OPENAI_API_KEY)
model_name = "gpt-4"

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
    # get route first:
    response = client.chat.completions.create(
        model=model_name,
        messages=[
            {"role": "system", "content": f"""You are a helpful tour guide who is working in {zoo_name}. 
             Your task is to give a list of attractions that may interest a visitor.
             You can only select attractions in this list: [{zoo_places_list}],  
             Avoid selecting toilets/water points, tram stops, nursing rooms and shops unless requested. 
             Ensure the names are encased in single apostrophies, as given in the list.
             Reply with only the list."""},
            {"role": "user", "content": user_input}
        ],
        temperature=0,
    )
    route = response.choices[0].message.content.strip()
    return jsonify({'response': route}) 

# end point to use LLM to structure route as response
@app.route('/get_text', methods=['POST'])
def get_text():
    try:
        # Get the 'route' data from the request JSON
        route = request.json['route']
        # Continue with your processing
        response = client.chat.completions.create(
            model=model_name,
            messages=[
                {"role": "system", "content": f"""You are a tour guide at {zoo_name}. 
                 Your task is to talk to a visitor, telling them the attractions they will visit in the sequence given in the following list.
                 Keep you response succint, and ensure the names of the attractions are encsed in single apostrophies, as given in the list."""},
                {"role": "user", "content": str(route)}
            ],
            temperature=0,
        )
        print(response.choices[0].message.content.strip())
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
    places = [place.strip('[] ').replace("'", "") for place in places]
    coordinates = []
    for place in places:
        # Find the row in the DataFrame that matches the place name
        row = place_info_df[place_info_df['name'] == place]
        if not row.empty:
            coord = row['coordinate'].values[0]
            lng, lat = map(float, coord.split(';'))
            coordinates.append({'lng': lng, 'lat': lat})
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
        name = name.replace("'","")
        formatted_id = name.replace(' ', '-').lower()
        # Create the hyperlink HTML
        hyperlink = f'<a href="#" class="location-link" data-marker-id={formatted_id}>{name}</a>'
        hyperlinks[name] = hyperlink
    return hyperlinks


def insertHyperlinks(message, replacements):
    print(replacements)
    # Split the message into chunks by single apostrophes
    chunks = message.split("'")
    
    # Iterate through the chunks and replace matches
    for i in range(len(chunks)):
        chunk = chunks[i].strip()
        if chunk in replacements:
            chunks[i] = replacements[chunk]
    
    # Reconstruct the message
    return "'".join(chunks)

###########################################################################################################
if __name__ == '__main__':
    app.run(debug=True, port=5000)
