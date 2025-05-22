from openai import OpenAI
import json
import os
from api.data_apis import *

# Get the directory of the current file
current_dir = os.path.dirname(os.path.abspath(__file__))

# Construct the path to the config file
config_file_path = os.path.join(current_dir, '..', 'config.json')

# Read the config file
with open(config_file_path, 'r') as file:
    config = json.load(file)
client = OpenAI(api_key=config["OPENAI_API_KEY"])
model_name = config['GPT_MODEL']

def basic_prompt(user_input,chat_history):
    prompt = f"""
    You are a helpful assistant. Respond to the user's query as well as possible.
    Chat history:
    {chat_history}
    """
    messages = [
        {"role": "system", "content": prompt},
        {"role": "user", "content": user_input}
    ]
    response = client.chat.completions.create(
        model=model_name,
        messages=messages,
    )
    message = response.choices[0].message
    return message

def wayfind_prompt(user_input, chat_history, poi_data):
    # fetch poi info
    prompt = f"""
    You are a helpful assistant. The user is trying to locate a place of interest. 
    Refer to the following data related to the POI to most accurately determine the location of the POI. 
    The user only needs the floor, unit number and current opening status of the store. If the opening status is unavailable, give the operating hours instead. Omit any unavailable information.
    The user will be provided a button below your response to generate a navigation aid. Inform them to "Click the button to find out how to get there!".
    POI Data: {poi_data}
    Chat history:
    {chat_history}
    """
    messages = [
        {"role": "system", "content": prompt},
        {"role": "user", "content": user_input}
    ]
    response = client.chat.completions.create(
        model=model_name,
        messages=messages,
    )
    message = response.choices[0].message
    return message

def intro_prompt(user_input, chat_history, poi_data):
    # fetch poi info
    prompt = f"""
    You are a helpful assistant. The user wants to know more about a POI. Give the user a brief introduction of the POI, including its name, description, and any other relevant information to a visitor.
    Refer to the following data related to the POI to most accurately respond to the user's query about the POI.
    POI Data: {poi_data}
    Chat history:
    {chat_history}
    """
    messages = [
        {"role": "system", "content": prompt},
        {"role": "user", "content": user_input}
    ]
    response = client.chat.completions.create(
        model=model_name,
        messages=messages,
    )
    message = response.choices[0].message
    return message

def nav_intro_prompt(user_input, chat_history, poi_data):
    # fetch poi info
    prompt = f"""
    You are a helpful assistant. The user wants to know more about a POI and how to get there. Give the user a brief introduction of the POI and its location. The location will be provided on the user's map UI.
    Refer to the following data related to the POI to most accurately respond to the user's query about the POI.
    POI Data: {poi_data}
    Chat history:
    {chat_history}
    """
    messages = [
        {"role": "system", "content": prompt},
        {"role": "user", "content": user_input}
    ]
    response = client.chat.completions.create(
        model=model_name,
        messages=messages,
    )
    message = response.choices[0].message
    return message

def rec_prompt(user_input, chat_history, poi_data):
    prompt = f"""
    You are a helpful assistant. The user wants you to reccommend some POIs to them based on their query. 
    The following data entails the shortlisted POIs to recommend the user: 
    POI Data: {poi_data}
    Generate a message to introfuce these POIs to the user.
    Chat history:
    {chat_history}
    """
    messages = [
        {"role": "system", "content": prompt},
        {"role": "user", "content": user_input}
    ]
    response = client.chat.completions.create(
        model=model_name,
        messages=messages,
    )
    message = response.choices[0].message
    return message