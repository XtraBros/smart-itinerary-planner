from openai import OpenAI
from helpers.text_processing import process_formatted_history, detect_nearby_intent
import json
import numpy as np
import pandas as pd
import os

current_dir = os.path.dirname(os.path.abspath(__file__))

# Construct the path to the config file
config_file_path = os.path.join(current_dir, '..', 'config.json')

with open(config_file_path, 'r') as file:
    config = json.load(file)
client = OpenAI(api_key=config["OPENAI_API_KEY"])
model_name = config['GPT_MODEL']

TASK_TYPES = ["generic", "navigation", "introduction", "recommendation", "itinerary"]

CLASSIFIER_PROMPT = """
You are a task classifier for a travel assistant app.
Classify the following user query into exactly one of these task types: "{task_types}", and tag if the query requires spatial data (e.g. nearby locations).
Structure your response as a dictionary with keys "task" and "spatial", where "task" is one of the task types, and "spatial" is a boolean indicating if spatial data is needed.
Rules:
- Always return only the task type, nothing else.
- If unsure, default to "generic".

When to use each task type:
- "generic": For general questions about the locale, culture, or any non-specific inquiries.
- "navigation": For questions about directions, locations, or how to get to a specific place.
- "introduction": For questions seeking information about a specific point of interest (POI).
- "recommendation": For requests for suggestions on places to visit, eat, or activities to do.
- "itinerary": For requests to plan a trip or create a schedule of activities.

User query: "{query}"
"""

def classify_task(query: str) -> str:
    messages = [
        {"role": "system", "content": CLASSIFIER_PROMPT.format(query=query, task_types=TASK_TYPES)},
        {"role": "user", "content": query}
    ]
    response = client.chat.completions.create(
        model=model_name,
        messages=messages,
    )
    response_text = response.choices[0].message.content.strip()
    message = json.loads(response_text)  # Keep the original casing
    task = message["task"].lower()  # lowercase only the task string
    spatial = message["spatial"]
    return task, spatial

class RetrievalStrategy:
    def fetch(self, rag_platform, query, context):
        raise NotImplementedError

class NormalRetrieval(RetrievalStrategy):
    def fetch(self, rag_platform, query, context):
        return rag_platform.query(query)

class SpatialRetrieval(RetrievalStrategy):
    def fetch(self, rag_platform, query, context):
        user_location = context.get("user_location")
        if not user_location:
            raise ValueError("User location required for spatial query")
        return rag_platform.spatial_query(user_location, query)


def handle_generic(app, query: str, user_location: str, spatial_type: bool = False) -> dict:
    """
    Generic catch-all Q&A handler.
    Example use case: free-form questions that don’t fit other categories.
    """
    locale_name, history = app.locale_names, process_formatted_history(app.memory.load_memory_variables({}))
    prompt =f"""
You are a helpful assistant from {locale_name}. Answer all questions pertaining to the locale you are assigned to, and do not answer questions outside of this context.
If you are unsure of how to answer, you should ask the user for more information.
Chat history:
{history}
User location: {user_location}
        """
    messages = [
        {"role": "system", "content": prompt},
        {"role": "user", "content": query}
    ]
    response = client.chat.completions.create(
        model=model_name,
        messages=messages,
    )
    response = response.choices[0].message.content.strip()
    return {'response' : response, "poi_data": []}


def handle_navigation(app, query: str, user_location: str, spatial_type: bool = False) -> dict:
    """
    Navigation handler.
    Example use case: 'How do I get to xx place?' or 'Where is the nearest yy?'
    """
    # Retrieval
    rpm, locale_name, history = app.rpm, app.locale_names, process_formatted_history(app.memory.load_memory_variables({}))
    intent = "spatial" if spatial_type else "semantic"
    poi_data = rpm.decide_retrieval(
        query_text=query,
        lat=user_location["lat"],
        lon=user_location["lng"],
        top_k=10,
        intent=intent
    )
    poi_data = [
        {k: (v.item() if isinstance(v, np.generic) else (None if pd.isna(v) else v))
        for k, v in poi.items()}
        for poi in poi_data
    ]
    # Response Generation
    prompt = f"""
    You are a helpful assistant working in {locale_name}. The user wants to know how to get to a given place. Give the user a brief introduction of the POI. The location will be provided on the user's map UI.
    Refer to the following data related to the POI to most accurately respond to the user's query about the POI, and inform them that the POI has been marked on their map.
    User location: {user_location}
    POI Data: {poi_data}
    Chat history:
    {history}
    """    
    messages = [
        {"role": "system", "content": prompt},
        {"role": "user", "content": query}
    ]
    response = client.chat.completions.create(
        model=model_name,
        messages=messages,
    )
    response = response.choices[0].message.content.strip()
    return {'response' : response, "poi_data": poi_data}


def handle_introduction(app, query: str, user_location: str, spatial_type: bool = False) -> dict:
    """
    Introduction of POIs
    """
    rpm, locale_name, history = app.rpm, app.locale_names, process_formatted_history(app.memory.load_memory_variables({}))
    intent = "spatial" if spatial_type else "semantic"
    poi_data = rpm.decide_retrieval(
        query_text=query,
        lat=user_location["lat"],
        lon=user_location["lng"],
        top_k=10,
        intent=intent
    )
    poi_data = [
        {k: (v.item() if isinstance(v, np.generic) else (None if pd.isna(v) else v))
        for k, v in poi.items()}
        for poi in poi_data
    ]
    prompt =  f"""
You are a helpful assistant working in {locale_name}. The user wants to know more about a POI. Give the user a brief introduction of the POI, including its name, description, and any other relevant information to a visitor. DO NOT give coordinate locations.
Refer to the following data related to the POI to most accurately respond to the user's query about the POI.
POI Data: {poi_data}
Chat history:
{history}
"""
    messages = [
        {"role": "system", "content": prompt},
        {"role": "user", "content": query}
    ]
    response = client.chat.completions.create(
        model=model_name,
        messages=messages,
    )
    response = response.choices[0].message.content.strip()
    return {'response' : response, "poi_data": poi_data}



def handle_recommendation(app, query: str, user_location: str, spatial_type: bool = False) -> dict:
    """
    Recommendation handler.
    Example use case: 'Suggest some restaurants near Clarke Quay'
    Workflow idea:
    - Extract category/location
    - Query recommendation engine (LLM or curated DB)
    - Rank results
    - Return structured list
    """
    rpm, locale_name, history = app.rpm, app.locale_names, process_formatted_history(app.memory.load_memory_variables({}))
    intent = "spatial" if spatial_type else "semantic"
    poi_data = rpm.decide_retrieval(
        query_text=query,
        lat=user_location["lat"],
        lon=user_location["lng"],
        top_k=10,
        intent=intent
    )
    poi_data = [
        {k: (v.item() if isinstance(v, np.generic) else (None if pd.isna(v) else v))
        for k, v in poi.items()}
        for poi in poi_data
    ]
    prompt = f"""
    You are a helpful assistant working in {locale_name}. The user wants recommendations for places to visit. Provide a list of recommended POIs with brief descriptions for each. DO NOT give coordinate locations.
    Refer to the following data related to the POI to most accurately respond to the user's query. Do not use any information outside of the provided data. If no data was provided, and the user requested for distance based recommendations, inform them that you are unable to find any suitable recommendations within their vicinity.
    POI Data: {poi_data}
    Chat history:
    {history}
    """
    messages = [
        {"role": "system", "content": prompt},
        {"role": "user", "content": query}
    ]
    response = client.chat.completions.create(
        model=model_name,
        messages=messages,
    )
    response = response.choices[0].message.content.strip()
    return {'response' : response, "poi_data": poi_data}



def handle_itinerary(query: str, context: dict) -> dict:
    """
    Itinerary planning handler.
    Example use case: 'Plan me a 3-day trip in Tokyo'
    Workflow idea:
    - Parse duration/locations/interests from query
    - Call itinerary planning engine
    - Assemble day-by-day schedule
    - Optionally support revisions/edits
    """
    # TODO: integrate itinerary planner workflow
    return {
        "task": "itinerary",
        "response": f"[Itinerary placeholder] for query: {query}",
        "metadata": {"plan": []}
    }

# Registry of task handlers
TASK_HANDLERS = {
    "generic": handle_generic,
    "navigation": handle_navigation,
    "introduction": handle_introduction,
    "recommendation": handle_recommendation,
    "itinerary": handle_itinerary,
}