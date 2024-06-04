# app.py

from flask import Flask, render_template, request, jsonify
from openai import OpenAI
import pandas as pd
from config import OPENAI_API_KEY

app = Flask(__name__)

client = OpenAI(api_key=OPENAI_API_KEY)
model_name = "gpt-4"

# Load data once when the server starts
place_info_df = pd.read_csv('zoo-info.csv')
place_info_df.columns = place_info_df.columns.str.strip()
place_info_df['name'] = place_info_df['name'].str.strip()
place_info_df['coordinate'] = place_info_df['coordinate'].str.strip().str.replace('(', '').str.replace(')', '')

zoo_name = "Singapore Zoo"
zoo_places_list = str(place_info_df['name'].unique())

sentosa_name = "Singapore Sentosa Island"
sentosa_places_list = "Entrance, Exit, Shangri La, Fort Siloso, SEA Aquarium, Palawan Beach, Tanjong Beach, Sentosa Golf Club, W Singapore, Capella Singapore, Universal Studios Singapore"

@app.route('/')
def home():
    return render_template('index.html', places=place_info_df)

@app.route('/ask_plan', methods=['POST'])
def ask_plan():
    user_input = request.json['message']
    response = client.chat.completions.create(
        model=model_name,
        messages=[
            {"role": "system", "content": f"You are a helpful tour guide who is working in {zoo_name}. Your task is to answer visitors' questions about how to plan their trip in this place. You must only give trip plan by using the names of attractions in this list: [{zoo_places_list}]. If not specified, the visitors will start from the Entrance and end at the Exit by default. But the Entrance and Exit should not be counted as attractions/amenities."},
            {"role": "user", "content": user_input}
        ],
        temperature=0,
    )
    return jsonify({'response': response.choices[0].message.content.strip()})

@app.route('/get_route', methods=['POST'])
def get_route():
    user_input = request.json['message']
    response = client.chat.completions.create(
        model=model_name,
        messages=[
            {"role": "system", "content": f"You are given a trip plan of this place: {zoo_name}. Your task is to analyze the plan and output a list of names of all attractions/amenities into a pair of brackets, and separate them by commas. You must only list the names that exist in the given list: [{zoo_places_list}]. They should also be in the same order as they appear in the trip plan. If not specified, the visitors will start from the Entrance and end at the Exit by default. So they should alsl be included in the list by default even if they are not mentioned explicitly. Here is an example resulting list: [Entrance, Place A, Place B, Place C, Exit]"},
            {"role": "user", "content": user_input}
        ],
        temperature=0,
    )
    return jsonify({'response': response.choices[0].message.content.strip()})

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

# Route to load POI info from csv file onto map
@app.route('/place_info', methods=['POST'])
def place_info():
    places = request.json['places']
    places = [place.strip('[] ').replace("'", "") for place in places]
    # Split the coordinates into separate columns
    filtered_df = place_info_df[place_info_df['name'].isin(places)]
    # Convert the dataframe to a list of dictionaries
    places = filtered_df[['name','description']].set_index('name')['description'].to_dict()
    # return {'name':'description'} 
    print(places)
    return jsonify(places)

if __name__ == '__main__':
    app.run(debug=True, port=5000)
