# app.py

from flask import Flask, render_template, request, jsonify
from openai import OpenAI
import pandas as pd

app = Flask(__name__)

openai_api_key = 'sk-proj-FUc3D3gTXzP2mOeZYYi6T3BlbkFJ7asHZq1wYYiNBsgyxXp3'
client = OpenAI(api_key=openai_api_key)

# Load data once when the server starts
zoo_info_df = pd.read_csv('zoo-info.csv')
zoo_info_df.columns = zoo_info_df.columns.str.strip()
zoo_info_df['name'] = zoo_info_df['name'].str.strip()
zoo_info_df['coordinate'] = zoo_info_df['coordinate'].str.strip().str.replace('(', '').str.replace(')', '')

@app.route('/')
def home():
    return render_template('test.html')

@app.route('/ask_plan', methods=['POST'])
def ask_plan():
    user_input = request.json['message']
    response = client.chat.completions.create(
        model="gpt-4",
        messages=[
            {"role": "system", "content": "You are a helpful tour guide who is working in Singapore Zoo. Your job is to answer visitors' questions about itinerary planning. You must only give itinerary plan for the following places of the zoo, (Entrance, Exit, Ah Meng Restaurant, KidzWorld, RepTopia, Giant Panda Forest, Animal Playground, White Rhinoceros, Pavilion By The Lake)."},
            {"role": "user", "content": user_input}
        ],
        temperature=0,
    )
    return jsonify({'response': response.choices[0].message.content.strip()})

@app.route('/get_route', methods=['POST'])
def get_route():
    # print(request.json)
    user_input = request.json['message']
    response = client.chat.completions.create(
        model="gpt-4",
        messages=[
            {"role": "system", "content": "You are given an itinerary plan, your task is to analyze the plan and output a list all places into a pair of brackets, and separate them by commas. You must only list the places that exist in the given list, which is (Entrance, Exit, Ah Meng Restaurant, KidzWorld, RepTopia, Giant Panda Forest, Animal Playground, White Rhinoceros, Pavilion By The Lake). They should also be in the same order as they appear in the itinerary plan. Example list: (Entrance, Giant Panda Forest, KidzWorld, Ah Meng Restaurant, Exit)"},
            {"role": "user", "content": user_input}
        ],
        temperature=0,
    )
    return jsonify({'response': response.choices[0].message.content.strip()})

@app.route('/get_coordinates', methods=['POST'])
def get_coordinates():
    places = request.json['places']  # This expects a list of place names
    print("places: ", places)
    filtered_data = zoo_info_df[zoo_info_df['name'].isin(places)]
    coordinates = filtered_data['coordinate'].tolist()  # Assuming 'coordinate' column has 'lat;lng'
    formatted_coordinates = [{'lat': float(coord.split(';')[0]), 'lng': float(coord.split(';')[1])} for coord in coordinates]
    print("coordinates: ", formatted_coordinates)
    return jsonify(formatted_coordinates)

if __name__ == '__main__':
    app.run(debug=True)