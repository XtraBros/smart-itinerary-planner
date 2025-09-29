from openai import OpenAI
from helpers.text_processing import process_formatted_history
import json
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
Classify the following user query into exactly one of these task types: "{task_types}".

Rules:
- Always return only the task type, nothing else.
- If unsure, default to "generic".

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
    message = response.choices[0].message.content.strip().lower()
    return message

def handle_generic(app, query: str, user_location: str) -> dict:
    """
    Generic catch-all Q&A handler.
    Example use case: free-form questions that don’t fit other categories.
    """
    locale_name, history = app.locale_name, process_formatted_history(app.memory.load_memory_variables({}))
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


def handle_navigation(app, query: str, user_location: str) -> dict:
    """
    Navigation handler.
    Example use case: 'How do I get to xx place?' or 'Where is the nearest yy?'
    """
    # Retrieval
    rag, locale_name, history = app.rag, app.locale_names, process_formatted_history(app.memory.load_memory_variables({}))
    poi_data = rag.query_by_name(query, top_k=5)
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


def handle_introduction(app, query: str, user_location: str) -> dict:
    """
    Introduction of POIs
    """
    rag, locale_name, history = app.rag, app.locale_name, process_formatted_history(app.memory.load_memory_variables({}))
    poi_data = rag.query_by_description(query, top_k=5)
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



def handle_recommendation(app, query: str, context: dict) -> dict:
    """
    Recommendation handler.
    Example use case: 'Suggest some restaurants near Clarke Quay'
    Workflow idea:
    - Extract category/location
    - Query recommendation engine (LLM or curated DB)
    - Rank results
    - Return structured list
    """
    rag, locale_name, history = app.rag, app.locale_name, process_formatted_history(app.memory.load_memory_variables({}))
    poi_data = rag.hybrid_query(query, top_k=5)
    prompt = f"""
    You are a helpful assistant working in {locale_name}. The user wants recommendations for places to visit. Provide a list of recommended POIs with brief descriptions for each. DO NOT give coordinate locations.
    Refer to the following data related to the POI to most accurately respond to the user's query.
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