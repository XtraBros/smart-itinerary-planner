from openai import OpenAI
from helpers.text_processing import process_formatted_history, detect_nearby_intent
from helpers.pref import get_user_preferences
from helpers.poi_graph_mapbox import suggest_waypoint_pois
from helpers.graph_manager import ensure_mapbox_graph
import json
import numpy as np
import pandas as pd
import os
import traceback
from langchain.memory import ConversationBufferWindowMemory
from langchain.schema import BaseMessage


current_dir = os.path.dirname(os.path.abspath(__file__))

# Construct the path to the config file
config_file_path = os.path.join(current_dir, '..', 'config.json')

with open(config_file_path, 'r') as file:
    config = json.load(file)
client = OpenAI(api_key=config["OPENAI_API_KEY"])
model_name = config['GPT_MODEL']

TASK_TYPES = ["generic", "navigation", "introduction", "recommendation", "itinerary", "waypoint"]

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
- "waypoint": For queries asking to visit or discover POIs along a route between two other POIs (e.g., "find a cafe on my way from A to B").

Return ONLY valid JSON in this exact format:
{{"task": "<one of {task_types}>", "spatial": <true or false>}}

User's first message:
"{first_user_message}"

Latest user message:
"{latest_user_message}"

Conversation history (other prior messages):
{chat_history}
"""

WAYPOINT_EXTRACTION_PROMPT = """
You extract structured information for users who want to visit a POI while travelling between two other POIs.
Return ONLY JSON with the format:
{{
  "start": "<starting point or empty string>",
  "end": "<ending point or empty string>",
  "categories": ["category words inferred from the request"],
  "tags": ["tag keywords inferred from the request"],
  "needs_clarification": <true or false>,
  "clarification_message": "<message to ask the user for missing info>"
}}

Rules:
- If the user explicitly names start and end, keep them verbatim.
- If either start or end is missing or ambiguous, set "needs_clarification" to true and craft a concise question in "clarification_message".
- Derive categories or tags from the requested POI type (e.g., "coffee shop" -> category "coffee shop", tag "coffee").
- Use the conversation history for additional context, but the latest user request has priority.
- Snap the user's intent to actual POIs using this retrieved data. Use the names of POIs as given in the POI data.

Conversation history:
{chat_history}

Latest user request:
{query}

Relevant POI data (JSON):
{poi_json}
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


def extract_waypoint_request(app, query: str, user_location: dict):
    history = process_formatted_history(app.memory.load_memory_variables({}))
    poi_df = getattr(app, "poi_df", None)
    fallback_data = []
    if poi_df is not None and not poi_df.empty:
        fallback_data = normalize_poi_data(poi_df.head(30).to_dict(orient="records"))

    rpm = getattr(app, "rpm", None)
    retrieved_data = fallback_data
    if rpm is not None:
        try:
            kwargs = {"query_text": query, "top_k": 20, "intent": "semantic"}
            if user_location and user_location.get("lat") is not None and user_location.get("lng") is not None:
                kwargs["lat"] = user_location["lat"]
                kwargs["lon"] = user_location["lng"]
            raw = rpm.decide_retrieval(**kwargs)
            normalized = normalize_poi_data(raw)
            if normalized:
                retrieved_data = normalized
        except Exception:
            traceback.print_exc()

    poi_json = json.dumps(retrieved_data[:30], ensure_ascii=False)
    # print(poi_json)
    prompt = WAYPOINT_EXTRACTION_PROMPT.format(
        chat_history=history,
        query=query,
        poi_json=poi_json
    )
    response = client.chat.completions.create(
        model=model_name,
        messages=[
            {"role": "system", "content": prompt},
            {"role": "user", "content": query},
        ],
    )
    text = response.choices[0].message.content.strip()
    print(text)
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        data = {
            "start": "",
            "end": "",
            "categories": [],
            "tags": [],
            "needs_clarification": True,
            "clarification_message": "Could you tell me where you are starting from and where you are headed?",
        }

    if not data.get("start") or not data.get("end"):
        data["needs_clarification"] = True
        if not data.get("clarification_message"):
            data["clarification_message"] = "Could you tell me which POIs you're starting from and heading to?"

    return data


class RetrievalStrategy:
    def fetch(self, rag_platform, query, context):
        raise NotImplementedError

class NormalRetrieval(RetrievalStrategy):
    def fetch(self, rag_platform, query, context):
        return rag_platform.query_combined(query)

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
    persona = app.llm_config.get("persona_instructions", "")
    prompt = f"""
You are a helpful assistant from {locale_name}. Answer all questions pertaining to the locale you are assigned to, and do not answer questions outside of this context. Do not provide any information that is not supported by data. Do NOT provide any POI information in this response.
If you are unsure of how to answer, ask the user for more information. Structure using HTML formatting (no ```html fences), but do not use bullet points.
Persona instructions: {persona}
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
    persona = app.llm_config.get("persona_instructions", "")
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
Structure using HTML formatting (no ```html fences), but do not use bullet points.
Persona instructions: {persona}
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
    persona = app.llm_config.get("persona_instructions", "")
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
Persona instructions: {persona}
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
    persona = app.llm_config.get("persona_instructions", "")
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
Persona instructions: {persona}
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


def handle_waypoint(app, query: str, user_location: dict, spatial_type: bool = False):
    extraction = extract_waypoint_request(app, query, user_location)
    start = extraction.get("start", "").strip()
    end = extraction.get("end", "").strip()
    categories = extraction.get("categories") or []
    tags = extraction.get("tags") or []
    needs_clarification = extraction.get("needs_clarification") or not (start and end)
    clarification = extraction.get("clarification_message") or "Could you tell me your starting point and destination?"

    if needs_clarification:
        yield {"type": "content", "content": clarification}
        app.memory.save_context({"input": query}, {"output": clarification})
        yield {"type": "done", "task": "waypoint"}
        return

    try:
        graph_data = ensure_mapbox_graph(app)
        result = suggest_waypoint_pois(
            start,
            end,
            graph_data["nodes"],
            graph_data["edges"],
            app.poi_df,
            categories=categories,
            tags=tags,
        )
    except Exception as exc:
        message = f"I couldn't look up graph routes right now: {exc}"
        yield {"type": "content", "content": message}
        app.memory.save_context({"input": query}, {"output": message})
        yield {"type": "done", "task": "waypoint"}
        return

    poi_payload = []
    for cand in result.get("candidates", []):
        details = cand["poi"]["details"].copy()
        details["detour_m"] = cand["detour_m"]
        details["total_distance_m"] = cand["total_distance_m"]
        poi_payload.append(details)

    fallback = result.get("fallback")
    if not poi_payload and fallback:
        details = fallback["poi"]["details"].copy()
        details["detour_m"] = fallback["detour_m"]
        details["total_distance_m"] = fallback["total_distance_m"]
        poi_payload.append(details)

    yield {"type": "poi_data", "content": poi_payload}

    if result.get("candidates"):
        best = result["candidates"][0]
        detour_text = f"about {int(best['detour_m'])} metres" if best["detour_m"] else "a very small"
        reply = (
            f"I found {best['poi']['name']} between {start} and {end}. "
            f"It only adds {detour_text} of detour and keeps you on track."
        )
    elif fallback:
        reply = (
            f"I couldn't keep the detour under the preferred limit, but {fallback['poi']['name']} "
            f"is the closest option between {start} and {end}. "
            f"It would add roughly {int(fallback['detour_m'])} metres."
        )
    else:
        reply = (
            f"I couldn't find a POI that fits your request along the route from {start} to {end}. "
            "Would you like me to search the general area instead?"
        )

    yield {"type": "content", "content": reply}
    app.memory.save_context({"input": query}, {"output": reply})
    yield {"type": "done", "task": "waypoint"}


# Registry of task handlers
TASK_HANDLERS = {
    "generic": handle_generic,
    "navigation": handle_navigation,
    "introduction": handle_introduction,
    "recommendation": handle_recommendation,
    "itinerary": handle_itinerary,
    "waypoint": handle_waypoint,
}
