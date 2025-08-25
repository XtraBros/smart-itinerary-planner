import json
import os
from datetime import datetime
from helpers.text_processing import remove_code_blocks
from typing import List, Dict
from helpers.route_solver import solve_route_with_balltree, reorder_and_extract_names

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
    "DD-MM-YYY": {{
        "HH-MM": "activity1",
        "HH-MM": "activity2",
        ...
        "notes": "additional notes or empty string"
    }}
    }}
    '''
    # prompt += "\n\n Ensure the operating hours of the POIs match the allocated time slot, but do not explicitly mention the operating hours or coordinate locations of the POIs. Ensure all information is simple and easily digestable by the user."
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

def fill_itinerary_skeleton(llm, pois, poi_order, schema, skeleton, user_input=None):
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

    - Fill in the itinerary with activities, following the order: {poi_order}.
    - Ensure activities are within the operating hours of the POIs, and that each time slot is given at least 1 hour. Fit as many POIs as possible into the plan. Prioritise promoting POIs over fulfilling the user's interests.
    - Fill up all activity slots with valid attractions from the give data, and avoid suggesting generic activities. Always use the POI names as activity names, and use the POI names exactly as given.
    - Add notes, reminders, or special considerations (e.g., breaks, accessibility, weather preferences),
    - Respect the trip dates, available hours, pace preference, and other user constraints,
    - For each POI, provide a brief description of the POI afgter giving its name as the activity.
    - Avoid any must_avoid or excluded_activities mentioned in the schema
    - Only recommend dining options if the timeslot is allocated for meals. All other slots should include activities or attractions. The only exception is for cafes, which can be included in any slot.
    Return the filled itinerary as a JSON object with this structure:
    {{
    "DD-MM-YYY": {{
        "HH-MM": "activity1",
        "HH-MM": "activity2",
        ...
        "notes": "additional notes or empty string"
    }}
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

    # Only attempt to parse if it's a string
    if isinstance(travel_plan, str):
        try:
            travel_plan = json.loads(travel_plan)
        except json.JSONDecodeError:
            raise ValueError("Invalid JSON string passed to json_to_itinerary_text.")

    # At this point, travel_plan should be a dict
    if not isinstance(travel_plan, dict):
        raise ValueError("Input must be a JSON string or a dictionary.")

    # Sort dates assuming DD-MM-YYYY
    sorted_days = sorted(travel_plan.items(), key=lambda x: tuple(map(int, x[0].split('-')[::-1])))

    output = ["Here is my recommended travel itinerary:"]

    for date_str, day_data in sorted_days:
        output.append(f"{date_str}:")
        time_keys = sorted(k for k in day_data.keys() if k != "notes")
        for time in time_keys:
            activity = day_data[time]
            output.append(f"  {time} - {activity}")
        notes = day_data.get("notes", "").strip()
        if notes:
            output.append(f"  Note: {notes}")
    output.append('''This plan focuses on introducing places you may be interested in. I have also marked some other attractions you may be interested in on your map!\nFor dining recommendations, let me know where you will be and I can find some nearby options for you. \nLet me know if you would like to further customize the plan!''')

    return "\n".join(output)

def edit_itinerary(llm, previous_itinerary: str, user_input: str, poi_data: List[Dict]) -> str:
    """
    Uses the LLM to edit the itinerary based on user instructions and relevant POI data.
    Returns the updated itinerary as plain text.
    """
    poi_descriptions = "\n".join(
        f"- {poi['name']}: {poi.get('description', 'No description available.')}"
        for poi in poi_data
    )

    prompt = f"""
    You are a helpful assistant for a travel planning app. A user has an existing itinerary and is asking to make changes.
    You should carefully follow their instructions while maintaining a realistic and enjoyable travel experience.

    --- Previous Itinerary ---
    {previous_itinerary}

    --- User Request ---
    {user_input}

    --- Relevant POI Data ---
    {poi_descriptions}

    Please revise the itinerary according to the user’s request. Maintain time slots if possible, and keep a similar format to the original.

    Respond only with the updated itinerary in plain text.
    """

    messages = [
        {"role": "system", "content": "You are an expert travel assistant that edits itineraries based on user instructions."},
        {"role": "user", "content": prompt}
    ]

    response = llm.invoke(messages)
    return remove_code_blocks(response)

def plan_itinerary(app, rag, llm, user_input, data):
    schema = load_schema()
    skeleton = generate_skeleton(llm, schema, user_input)
    pois = rag.query_by_tags(extract_rag_tags(schema), attractions_only=True, top_k=5*get_trip_duration_days(schema))
    dining = rag.itinerary_dining_search(schema)
    print(f" Dining RAG =====> {dining}")
    pois.extend(dining)
    if data["notes"]:
        pois1 = rag.query(data["notes"], attractions_only=True)
        pois = pois + pois1
        pois = list({poi["name"]: poi for poi in pois}.values())
    pois_order = solve_route_with_balltree([poi['name'] for poi in pois], app.poi_df, app.balltree)
    pois_order = reorder_and_extract_names(pois, pois_order)
    itinerary = fill_itinerary_skeleton(llm, skeleton, pois, pois_order, schema, user_input)
    response = json_to_itinerary_text(remove_code_blocks(itinerary))
    return response