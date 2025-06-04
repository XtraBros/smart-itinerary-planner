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
    # prompt += "\n\nPlease generate a filled-out version of an itinerary. You may use placeholders if user input is insufficient."
    response = llm.invoke(prompt)
    return response

def extract_tags_from_trip_schema(schema: dict) -> list:
    tags = []

    # Basic trip info
    if schema.get("trip_title"):
        tags.append(schema["trip_title"])

    # Group details
    if schema.get("group_type"):
        tags.append(schema["group_type"])
    if schema.get("has_children"):
        tags.append("has_children")
        if schema.get("children_ages"):
            tags.append("children_" + schema["children_ages"])
    if schema.get("has_elderly"):
        tags.append("has_elderly")
        if schema.get("elderly_needs"):
            tags.append("elderly_" + schema["elderly_needs"])
    if schema.get("accessibility_needs"):
        tags.append("accessibility_" + schema["accessibility_needs"])

    # Preferences
    if schema.get("pace_preference"):
        tags.append(schema["pace_preference"].lower().replace("-", "_"))
    if schema.get("interests"):
        tags.extend([interest.strip().lower() for interest in schema["interests"].split(",")])
    if schema.get("dining_preference"):
        tags.append("dining_" + schema["dining_preference"].lower())
    if schema.get("transport"):
        tags.append("transport_" + schema["transport"].lower())

    # Time-related preferences
    if schema.get("break_frequency"):
        tags.append("breaks_" + schema["break_frequency"].lower().replace(" ", "_"))
    if schema.get("meal_times"):
        tags.extend([f"meal_{t.strip()}" for t in schema["meal_times"].split(",") if t.strip()])

    # Constraints
    for key in ["must_visit", "must_avoid", "prebooked", "excluded_activities"]:
        if schema.get(key):
            tags.extend([f"{key}_{item.strip().lower()}" for item in schema[key].split(",")])

    # Weather-related
    if schema.get("weather_preference"):
        tags.append("weather_" + schema["weather_preference"].lower())
    if schema.get("avoid_heat"):
        tags.append("avoid_heat")
    if schema.get("backup_plan"):
        tags.append("has_backup_plan")

    # Additional notes
    if schema.get("additional_notes"):
        tags.extend([note.strip().lower() for note in schema["additional_notes"].split(",") if note.strip()])

    # Flatten and deduplicate
    flat_tags = set()
    for tag in tags:
        if isinstance(tag, list):
            flat_tags.update(tag)
        else:
            flat_tags.add(tag.strip())

    return list(flat_tags)

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