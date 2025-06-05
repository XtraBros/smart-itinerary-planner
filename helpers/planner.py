import json
import os
from datetime import datetime

def load_schema(schema_path="./data/user_schema.json"):
    def convert_value(value):
        # Try to convert to int
        if isinstance(value, str):
            value = value.strip()
            if value.isdigit():
                return int(value)
            try:
                return float(value)
            except ValueError:
                pass
            try:
                # Try ISO datetime formats
                return datetime.fromisoformat(value)
            except ValueError:
                pass
        return value

    def convert_structure(obj):
        if isinstance(obj, dict):
            return {k: convert_structure(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [convert_structure(i) for i in obj]
        else:
            return convert_value(obj)

    if not os.path.exists(schema_path):
        raise FileNotFoundError(f"Schema file not found at: {schema_path}")

    with open(schema_path, "r") as f:
        raw = json.load(f)
        return convert_structure(raw)
    
def generate_skeleton(llm, schema, user_input=None):
    prompt = "You are an intelligent itinerary planning assistant. Based on the following schema, generate a JSON object to serve as a planning skeleton. "
    if user_input:
        prompt += f"\nUser input: {user_input}"
    prompt += "\n\nAdditional Constraints:\n" + f"{schema}"
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
    prompt += "/n/n Ensure the operating hours of the POIs match the allocated time slot, but do not explicitly mention the operating hours or coordinate locations of the POIs. Ensure all information is simple and easily digestable by the user."
    # prompt += "\n\nPlease generate a filled-out version of an itinerary. You may use placeholders if user input is insufficient."
    messages = [
        {"role": "system", "content": prompt},
        {"role": "user", "content": user_input}
    ]
    response = llm.invoke(messages)
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

    # Budget level — safely handle empty strings and non-numeric
    budget = schema.get("daily_budget")
    if budget not in (None, ""):
        try:
            budget_num = float(budget)
            if budget_num < 50:
                tags.append("budget travel")
            elif 50 <= budget_num <= 150:
                tags.append("mid-range travel")
            else:
                tags.append("luxury travel")
        except (ValueError, TypeError):
            # If budget cannot be converted to a number, ignore it
            pass

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
    start_date = schema.get("start_date")
    end_date = schema.get("end_date")
    if not start_date or not end_date:
        return 0  # or raise an error if dates are mandatory

    duration = (end_date - start_date).days + 1  # +1 to include both start and end dates
    return duration

def fill_itinerary_skeleton(llm, pois, schema, skeleton, user_input=None):
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
    messages = [
        {"role": "system", "content": prompt},
        {"role": "user", "content": user_input}
    ]
    response = llm.invoke(messages)
    return response

def json_to_itinerary_text(travel_plan):
    import json

    if isinstance(travel_plan, str):
        try:
            travel_plan = json.loads(travel_plan)
        except json.JSONDecodeError:
            raise ValueError("Invalid JSON string passed to json_to_itinerary_text.")

    sorted_days = sorted(travel_plan.items(), key=lambda x: x[1]["date"])
    output = []

    for day_label, day_data in sorted_days:
        output.append("=" * 40)
        output.append(f"{day_label}")
        output.append(f"Date       : {day_data['date']}")

        if day_data.get("activities"):
            output.append("Activities :")
            for activity in day_data["activities"]:
                output.append(f"  - {activity}")

        if day_data.get("dining"):
            output.append(f"Dining     : {day_data['dining']}")

        if day_data.get("transport"):
            output.append(f"Transport  : {day_data['transport']}")

        if day_data.get("notes"):
            output.append(f"Notes      : {day_data['notes']}")

        output.append("=" * 40)
        output.append("")  # blank line

    return "\n".join(output)