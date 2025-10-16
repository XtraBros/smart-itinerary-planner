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

def generic_prompt(user_input,chat_history, app):
    prompt = f"""
    You are a helpful assistant from {app.locale_name}. Answer all questions pertaining to the locale you are assigned to, and do not answer questions outside of this context.
    If you are unsure of how to answer, you should ask the user for more information.
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

def nav_prompt(user_input, chat_history, poi_data):
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

def planning_prompt(user_input, chat_history, poi_data):
    prompt = f"""
    You are a helpful assistant. The user wants you to plan an itinerary for them based on their query. 
    The following data entails the shortlisted POIs to include in the itinerary: 
    POI Data: {poi_data}
    Generate a message to introduce these POIs to the user. For each POI, include a short description about it.
    Do not include any dining options unless specified by the user.
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