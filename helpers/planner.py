import json
import os
from datetime import datetime

def load_schema(schema_path="../data/user_schema.json"):
    with open(schema_path, "r") as f:
        return json.load(f)
    
def generate_skeleton(llm, schema, user_input=None):
    prompt = "You are an intelligent itinerary planning assistant. Based on the following schema, generate a JSON object to serve as a planning skeleton. "
    if user_input:
        prompt += f"\nUser input: {user_input}"
    prompt += "\n\nAdditional Constraints:\n" + json.dumps(schema, indent=2)
    prompt += f'''
    Return the filled itinerary as a JSON object with this structure:

    {{
    "Day 1 (YYYY-MM-DD)": {{
        "date": "YYYY-MM-DD",
        "activities": [ "activity1", "activity2", ... ],
        "dining": "dining option or empty string",
        "transport": "transport option or empty string",
        "notes": "additional notes or empty string"
    }},
    "Day 2 (YYYY-MM-DD)": {{
        ...
    }},
    ...
    }}
    '''
    # prompt += "\n\nPlease generate a filled-out version of an itinerary. You may use placeholders if user input is insufficient."
    response = llm.invoke(prompt)
    return response

def extract_rag_tags(schema: dict) -> list:
    """
    Extracts meaningful tags from the user itinerary schema
    for use in RAG or vector search.
    """
    tags = []

    # Include general trip context
    if schema.get("trip_title"):
        tags.append(schema["trip_title"])

    # Add group-related info
    group_type = schema.get("group_type")
    if group_type:
        tags.append(f"{group_type} group")
    if schema.get("has_children") is True:
        tags.append("family-friendly")
    elif schema.get("has_children") is False:
        tags.append("no children")

    group_size = schema.get("group_size")
    if group_size:
        if group_size == 1:
            tags.append("solo traveler")
        elif group_size <= 2:
            tags.append("small group")
        elif group_size > 4:
            tags.append("large group")

    # Dining preferences
    if schema.get("dining_preference"):
        tags.append(schema["dining_preference"])

    # Budget level
    budget = schema.get("daily_budget")
    if budget is not None:
        if budget < 50:
            tags.append("budget travel")
        elif 50 <= budget <= 150:
            tags.append("mid-range travel")
        else:
            tags.append("luxury travel")

    # Transport
    if schema.get("transport"):
        tags.append(f"prefers {schema['transport']} transport")

    # Time preferences (optional)
    if schema.get("start_time") and schema.get("end_time"):
        tags.append(f"active from {schema['start_time']} to {schema['end_time']}")

    # Additional notes
    if schema.get("additional_notes"):
        tags.append(schema["additional_notes"])

    return tags

def get_trip_duration_days(schema: dict) -> int:
    start_date_str = schema.get("start_date")
    end_date_str = schema.get("end_date")
    if not start_date_str or not end_date_str:
        return 0  # or raise an error if dates are mandatory

    start_date = datetime.strptime(start_date_str, "%Y-%m-%d")
    end_date = datetime.strptime(end_date_str, "%Y-%m-%d")

    duration = (end_date - start_date).days + 1  # +1 to include both start and end dates
    return duration

def fill_itinerary_skeleton(llm, pois, schema, skeleton):
    prompt = f'''
    You are a travel planner assistant.

    Given the following inputs:

    1. User Trip Schema:
    {schema}

    2. POI Data from RAG platform:
    {pois}

    3. Skeleton Itinerary:
    {skeleton}

    Your task is to fill in the itinerary details for each day. For each day, use the POI data and user schema preferences to:

    - Suggest activities to do during the day (use the POIs and any relevant activities),
    - Suggest dining options if available,
    - Suggest transport modes if not already fixed,
    - Add notes, reminders, or special considerations (e.g., breaks, accessibility, weather preferences),
    - Respect the trip dates, available hours, pace preference, and other user constraints,
    - Avoid any must_avoid or excluded_activities mentioned in the schema,
    - If some days have no POI data, provide general suggestions or keep empty lists.

    Return the filled itinerary as a JSON object with this structure:

    {{
    "Day 1 (YYYY-MM-DD)": {{
        "date": "YYYY-MM-DD",
        "activities": [ "activity1", "activity2", ... ],
        "dining": "dining option or empty string",
        "transport": "transport option or empty string",
        "notes": "additional notes or empty string"
    }},
    "Day 2 (YYYY-MM-DD)": {{
        ...
    }},
    ...
    }}

    Make sure the JSON is properly formatted and only return the JSON object, nothing else.
    '''
    response = llm.invoke(prompt)
    return response