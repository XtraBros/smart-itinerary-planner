from openai import OpenAI
from helpers.text_processing import process_formatted_history, detect_nearby_intent
from helpers.pref import get_user_preferences
import json
import numpy as np
import pandas as pd
import os
from langchain.memory import ConversationBufferWindowMemory
from langchain.schema import BaseMessage


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

Important: The **first user message** determines the main task of the conversation. Subsequent messages may provide details or preferences, but do NOT override the initial intent.

Decide which of the following task types best describe the conversation. Use exactly one of these task types: "{task_types}", 
and tag if the query requires spatial data (e.g. searching for POIs near the user's current location).

Structure your response as a dictionary with keys:
- "task": one of the task types
- "spatial": a boolean

Rules for spatial:
- Mark "spatial" as True ONLY if the query explicitly refers to the user's location or a relative area, 
  such as "near me", "close by", "around here", "within X metres/miles", "nearby", "in this area".
- Do NOT mark "spatial" as True if the query asks about a specific named place 
  (e.g., "Where is the xx Hotel?", "How do I get to Marina Bay Sands?").
- If unsure, default "spatial" to False.

When to use each task type:
- "generic": For general questions about the locale, culture, or any non-POI-specific inquiries.
- "navigation": For questions about directions, locations, or how to get to a specific place.
- "introduction": For questions seeking information about a specific point of interest (POI).
- "recommendation": For requests for suggestions on places to visit, eat, or activities to do.
- "itinerary": For requests to plan a trip or create a schedule of activities.

Return ONLY valid JSON in this exact format:
{{"task": "<one of {task_types}>", "spatial": <true or false>}}

User's first message:
"{first_user_message}"

Latest user message:
"{latest_user_message}"

Conversation history (other prior messages):
{chat_history}
"""

def normalize_poi_data(poi_data):
    return [
        {
            k: (
                v.item() if isinstance(v, np.generic)
                else (None if pd.isna(v) else v)
            )
            for k, v in poi.items()
        }
        for poi in poi_data
    ]

def get_first_user_message(memory) -> str:
    """
    Extract the first user message from a LangChain ConversationBufferWindowMemory object.
    """
    # Try structured messages first
    try:
        messages = memory.buffer_as_messages
        return messages[0].content
    except Exception as e:
        print("======>> No user message found in memory.")
        return ""

async def stream_generator(client, model_name, messages):
        full_reply = ""

        stream = await client.chat.completions.create(
            model=model_name,
            messages=messages,
            stream=True,
        )
        async for event in stream:
            delta = event.choices[0].delta.content
            if delta:
                full_reply += delta
                yield delta


def classify_task(app, query: str):
    # Get full history for context
    history = process_formatted_history(app.memory.load_memory_variables({}))

    # Extract first user message
    first_user_msg = get_first_user_message(app.memory)
    if not first_user_msg:
        first_user_msg = query  # fallback

    messages = [
        {"role": "system", "content": CLASSIFIER_PROMPT.format(
            first_user_message=first_user_msg,
            latest_user_message=query,
            task_types=TASK_TYPES,
            chat_history=history
        )},
        {"role": "user", "content": query}  # latest user message
    ]

    response = client.chat.completions.create(
        model= model_name,
        messages=messages,
    )

    response_text = response.choices[0].message.content.strip()
    message = json.loads(response_text)
    task = message["task"].lower()
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

def handle_generic(app, query: str, user_location: dict, spatial_type: bool = False):
    """
    Generic catch-all Q&A handler (synchronous streaming).
    Yields chunks as dictionaries for streaming in Flask.
    """
    locale_name = app.locale_names
    history = process_formatted_history(app.memory.load_memory_variables({}))

    prompt = f"""
You are a helpful assistant from {locale_name}. Answer all questions pertaining to the locale you are assigned to, and do not answer questions outside of this context. Do not provide any information that is not supported by data. Do NOT provide any POI information in this response.
If you are unsure of how to answer, ask the user for more information. Structure using HTML formatting (no ```html fences), but do not use bullet points.
Chat history:
{history}
User location: {user_location}
"""
    messages = [
        {"role": "system", "content": prompt},
        {"role": "user", "content": query}
    ]
    # Synchronous streaming using OpenAI client
    stream = client.chat.completions.create(
        model=model_name,
        messages=messages,
        stream=True,  # streaming enabled
    )

    # Return POI data (empty for generic)
    yield {"type": "poi_data", "content": []}

    full_reply = ""

    for chunk in stream:
        delta = chunk.choices[0].delta.content
        if delta:
            full_reply += delta
            yield {"type": "content", "content": delta}

    # Save to memory
    app.memory.save_context({"input": query}, {"output": full_reply})

    # Signal done
    yield {"type": "done", "task": "generic"}

def handle_navigation(app, query: str, user_location: dict, spatial_type: bool = False):
    """
    Navigation handler (sync streaming).
    """
    rpm = app.rpm
    locale_name = app.locale_names
    history = process_formatted_history(app.memory.load_memory_variables({}))

    intent = "spatial" if spatial_type else "semantic"
    poi_data = rpm.decide_retrieval(
        query_text=query,
        lat=user_location["lat"],
        lon=user_location["lng"],
        top_k=10,
        intent=intent
    )

    # normalize numpy/pd types
    poi_data = [
        {k: (v.item() if isinstance(v, np.generic) else (None if pd.isna(v) else v))
         for k, v in poi.items()}
        for poi in poi_data
    ]
    print(poi_data)
    # Yield POI data
    yield {"type": "poi_data", "content": poi_data}

    prompt = f"""
You are a helpful assistant working in {locale_name}. The user wants directions to a place.
Provide a brief introduction of the POI. Use the name of the POI exactly as given the the data. If no matching POI data is found, politely inform the user you could not find it.
Do NOT give the user instructions on how to get there, simply redirect them to their map display.
Refer to the following POI data to answer accurately, but do not include coordinates.
Structure using HTML formatting (no ```html fences), but do not use bullet points..
User location: {user_location}
POI Data: {poi_data}
Chat history:
{history}
"""
    messages = [
        {"role": "system", "content": prompt},
        {"role": "user", "content": query}
    ]

    stream = client.chat.completions.create(
        model=model_name,
        messages=messages,
        stream=True
    )

    full_reply = ""

    for chunk in stream:
        delta = chunk.choices[0].delta.content
        if delta:
            full_reply += delta
            yield {"type": "content", "content": delta}

    # Save to memory
    app.memory.save_context({"input": query}, {"output": full_reply})

    # Done
    yield {"type": "done", "task": "navigation"}


def handle_introduction(app, query: str, user_location: dict, spatial_type: bool = False):
    rpm = app.rpm
    locale_name = app.locale_names
    history = process_formatted_history(app.memory.load_memory_variables({}))
    intent = "spatial" if spatial_type else "semantic"

    # --- Retrieve POIs ---
    poi_data = rpm.decide_retrieval(
        query_text=query,
        lat=user_location["lat"],
        lon=user_location["lng"],
        top_k=10,
        intent=intent
    )
    poi_data = normalize_poi_data(poi_data)

    # Yield POI data
    yield {"type": "poi_data", "content": poi_data}

    # --- Prompt ---
    prompt = f"""
You are a helpful assistant from {locale_name}. The user wants an introduction to a POI.
Describe the POI clearly and concisely. Do NOT mention coordinates.

POI Data: {poi_data}

Chat history:
{history}
"""

    messages = [
        {"role": "system", "content": prompt},
        {"role": "user", "content": query}
    ]
    stream = client.chat.completions.create(
            model=model_name,
            messages=messages,
            stream=True
        )

    full_reply = ""

    for chunk in stream:
        delta = chunk.choices[0].delta.content
        if delta:
            full_reply += delta
            yield {"type": "content", "content": delta}

    # Save to memory
    app.memory.save_context({"input": query}, {"output": full_reply})

    # Done
    yield {"type": "done", "task": "introduction"}

def handle_recommendation(app, query: str, user_location: dict, spatial_type: bool = False):
    rpm = app.rpm
    locale_name = app.locale_names
    history = process_formatted_history(app.memory.load_memory_variables({}))
    intent = "spatial" if spatial_type else "semantic"

    poi_data = rpm.decide_retrieval(
        query_text=query,
        lat=user_location["lat"],
        lon=user_location["lng"],
        top_k=10,
        intent=intent
    )
    poi_data = normalize_poi_data(poi_data)
    # Yield POI data
    yield {"type": "poi_data", "content": poi_data}
    prompt = f"""
You are a helpful assistant working in {locale_name}. The user wants recommendations. Reply the user with a friendly tone, and provide a short ranked list of POIs with descriptions.
Do NOT give coordinates. Only use POIs from the provided data. Prioritize POIs with active experiences instead of dining, accomodationor shopping unless explicitly requested by the user.

POI Data: {poi_data}

If no POIs exist and the user requested distance-based results, politely say none were found.
Structure using HTML formatting (no ```html fences), but do not use bullet points..

Chat history:
{history}
"""

    messages = [
        {"role": "system", "content": prompt},
        {"role": "user", "content": query}
    ]

    stream = client.chat.completions.create(
        model=model_name,
        messages=messages,
        stream=True
    )

    full_reply = ""

    for chunk in stream:
        delta = chunk.choices[0].delta.content
        if delta:
            full_reply += delta
            yield {"type": "content", "content": delta}

    # Save to memory
    app.memory.save_context({"input": query}, {"output": full_reply})

    # Done
    yield {"type": "done", "task": "recommendation"}


def handle_itinerary(app, query: str, user_location: dict, spatial_type: bool = False):

    rpm = app.rpm
    locale_name = app.locale_names
    history = process_formatted_history(app.memory.load_memory_variables({}))
    intent = "spatial" if spatial_type else "semantic"

    # ----------------------------------------------------------------------
    # 1. PREFERENCE EXTRACTION (single prompt)
    # ----------------------------------------------------------------------

    pref_result = get_user_preferences(
        llm_client=client,
        model_name=model_name,
        query=query,
        chat_history=history
    )

    status = pref_result["status"]
    preferences = pref_result["preferences"]
    retrieval_query = pref_result.get("retrieval_query")
    clarification_message = pref_result.get("clarification_message")

    # ----------------------------------------------------------------------
    # 1B. Need user clarification
    # ----------------------------------------------------------------------
    if status == "need_clarification":

        yield {
            "type": "content",
            "content": clarification_message,
            "partial_preferences": preferences
        }

        # Memory save
        app.memory.save_context(
            {"input": query},
            {"output": clarification_message}
        )
        # finish
        yield {"type": "done", "task": "generic"}
        return

    # Save prefs
    app.session_state["preferences"] = preferences

    # ----------------------------------------------------------------------
    # 2. RETRIEVAL
    # ----------------------------------------------------------------------

    effective_query = retrieval_query if retrieval_query else query

    poi_data = rpm.decide_retrieval(
        query_text=effective_query,
        lat=user_location["lat"],
        lon=user_location["lng"],
        intent=intent
    )

    poi_data = normalize_poi_data(poi_data)

    # Stream POIs to frontend
    yield {"type": "poi_data", "content": poi_data}

    # ----------------------------------------------------------------------
    # 3. GENERATE ITINERARY (LLM streaming)
    # ----------------------------------------------------------------------

    itinerary_prompt = f"""
You are a helpful assistant. The user wants an itinerary.

User Preferences (extracted and structured):
{preferences}

Use ONLY the provided POIs to build a structured, clear itinerary.
Rules:
- Do NOT include entrances, exits, or ticketing details.
- Structure using HTML formatting (no ```html fences), but do not use bullet points..
- Maximum heading level allowed is <h2>.
- Do NOT use bullet points.
- Include short descriptions (1–2 sentences each).
- Do NOT include dining unless the user explicitly asked.
- Respect user preferences strictly.
- Prefer natural flow, geographical efficiency, and experience quality.

POI Data:
{poi_data}

Chat history:
{history}
"""

    messages = [
        {"role": "system", "content": itinerary_prompt},
        {"role": "user", "content": query}
    ]

    stream = client.chat.completions.create(
        model=model_name,
        messages=messages,
        stream=True
    )

    full_reply = ""

    for chunk in stream:
        delta = chunk.choices[0].delta.content
        if delta:
            full_reply += delta
            yield {"type": "content", "content": delta}


    # ----------------------------------------------------------------------
    # 4. MEMORY SAVE
    # ----------------------------------------------------------------------

    app.memory.save_context(
        {"input": query},
        {"output": full_reply}
    )
    yield {"type": "done", "task": "itinerary"}
    print("========== HANDLE ITINERARY END ==========\n")


# Registry of task handlers
TASK_HANDLERS = {
    "generic": handle_generic,
    "navigation": handle_navigation,
    "introduction": handle_introduction,
    "recommendation": handle_recommendation,
    "itinerary": handle_itinerary,
}