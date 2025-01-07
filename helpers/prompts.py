from openai import OpenAI
import json
from api.data_apis import *

CONFIG_FILE = '../config.json'
with open(CONFIG_FILE, 'r') as file:
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
    You are a helpful assistant. The user wants to know more about a POI. 
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
    Determine the 3 most suitable POIs to recommend, and generate a message to introduce them to the user.
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