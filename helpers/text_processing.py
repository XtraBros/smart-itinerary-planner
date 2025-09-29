import re
from rapidfuzz import process, fuzz
import json
import unicodedata
import math
from typing import Optional
def sanitize_for_json(obj):
    if isinstance(obj, dict):
        return {k: sanitize_for_json(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [sanitize_for_json(item) for item in obj]
    elif isinstance(obj, float) and math.isnan(obj):
        return None
    else:
        return obj

# Function to handle duplicated GPT output
def remove_dupes(response_text):
    # Use a regular expression to find all occurrences of dictionaries
    matches = re.findall(r'\{.*?\}', response_text)

    if matches:
        # Return only the first dictionary
        return matches[0]
    else:
        # If no dictionary is found, return the original response
        return response_text

# handle code chunks and ``` tags 

def remove_code_blocks(content):
    # Step 1: Remove language identifiers in code blocks (e.g., ```json, ```html), but keep the content inside
    cleaned_content = re.sub(r'```[a-zA-Z]+\n', '', content)
    
    # Step 2: Remove closing code block tags (```)
    cleaned_content = re.sub(r'```', '', cleaned_content)
    
    # Step 3: Remove escape sequences like \n (newline), \t (tab), etc.
    cleaned_content = cleaned_content.replace('\n', ' ').replace('\t', ' ')
    
    # Step 4: Remove multiple spaces caused by newline/tab replacements
    cleaned_content = re.sub(r'\s+', ' ', cleaned_content)
    
    return cleaned_content.strip()


def url_to_hyperlink(text):
    if isinstance(text,list):
        return text
    # Convert markdown-style links [text](url) to HTML
    markdown_pattern = r'\[([^\]]+)\]\((https?://[^\)]+)\)'
    text = re.sub(markdown_pattern, r'<a href="\2">\1</a>', text)
    
    # Convert plain URLs (that are not already part of a link)
    url_pattern = r'(?<!href=")(https?://[^\s]+)'
    text = re.sub(url_pattern, r'<a href="\1">\1</a>', text)
    
    return text

# Function to create hyperlinks for places
def create_hyperlinks(place_list, coordinates):
    hyperlinks = {}
    for index, name in enumerate(place_list):
        formatted_id = name.replace('"', '').replace(' ', '-').lower()
        # Create a dictionary for coordinates with 'lng' and 'lat' keys
        coord_dict = {"lng": coordinates[index][0], "lat": coordinates[index][1]}
        # Create the hyperlink HTML
        hyperlink = f'<a href="#" class="location-link" data-coordinates="{coord_dict}" data-marker-id="{formatted_id}">{name}</a>'
        hyperlinks[name] = hyperlink
    return hyperlinks


def insert_hyperlinks(message, replacements):
    # Split the message into chunks by the `~` delimiter
    chunks = message.split("~")
    # Replace chunks with hyperlinks where applicable
    chunks = map(lambda chunk: replacements.get(chunk.strip(), chunk), chunks)
    # Reconstruct the message by joining the mapped chunks
    final_message = "".join(chunks)
    # Step 1: Process numbered and bulleted lists
    final_message = format_paragraphs(final_message)
    return final_message

def mark_poi_names(text, poi_names):
    # Sort longer names first to avoid substring conflicts
    sorted_names = sorted(poi_names, key=len, reverse=True)

    for name in sorted_names:
        pattern = r'\b' + re.escape(name) + r'\b'
        text = re.sub(pattern, f'~{name}~', text)
    
    return text

def extract_poi_names_and_coords(poi_data):
    names = []
    coordinates = []
    for poi in poi_data:
        names.append(poi["name"])
        coordinates.append((poi["longitude"], poi["latitude"]))
    return names, coordinates

def hyperlink_pois_in_response(response_text, poi_data):
    names, coords = extract_poi_names_and_coords(poi_data)
    hyperlinks = create_hyperlinks(names, coords)
    marked_text = mark_poi_names(response_text, names)
    hyperlinked_response = insert_hyperlinks(marked_text, hyperlinks)
    return hyperlinked_response

def format_paragraphs(text):
    # Split text into paragraphs by double line breaks
    paragraphs = text.split('\n\n')
    # Wrap each paragraph in <p> tags and join them
    formatted_text = ''.join([f'<p>{p.strip()}</p>' for p in paragraphs])
    # Replace single line breaks with <br> for line breaks within a paragraph
    formatted_text = formatted_text.replace('\n', '<br>')
    return formatted_text

def process_formatted_history(history):
    if isinstance(history, dict) and "history" in history:
        history = history["history"]
    if not isinstance(history, str):
        raise ValueError("Expected history to be a string or dict containing 'history'")
    lines = history.strip().split("\n")
    processed_history = []
    
    for line in lines:
        # Check if it's an AI response line and attempt to parse it as JSON
        if line.startswith("AI:"):
            # Extract JSON part from the line
            ai_message_json = line[3:].strip()
            try:
                # Parse JSON and extract 'response'
                ai_message = json.loads(ai_message_json)
                response = ai_message.get("response", "")
                processed_history.append(f"AI: {response}")
            except json.JSONDecodeError:
                # If JSON is invalid, keep line as is
                processed_history.append(line)
        else:
            # For Human lines, keep them as they are
            processed_history.append(line)
    
    return "\n".join(processed_history)

def normalize(text):
    text = unicodedata.normalize('NFKD', text)  # Normalize characters
    text = re.sub(r'[^\w\s]', '', text)         # Remove special characters
    return text.strip().lower()                # Lowercase and strip whitespace

def match_names(names, dataframe, threshold=80):
    """
    Matches names from a list to the names in a pandas DataFrame, compensating for typos.
    
    Args:
        names (list): A list of names to match.
        dataframe (pd.DataFrame): A DataFrame with columns "name" and "poiId".
        threshold (int): Minimum similarity score (0-100) for a match.
        
    Returns:
        list: A list of poiIds where the name matches with the input names.
    """
    matched_poiIds = set()
    
    # Normalize the dataframe names
    dataframe['name_normalized'] = dataframe['name'].apply(normalize)
    
    for input_name in names:
        input_name_normalized = normalize(input_name)
        results = process.extract(
            input_name_normalized,
            dataframe['name_normalized'],
            scorer=fuzz.token_sort_ratio,
            limit=None
        )
        
        for match_name, score, index in results:
            if score >= threshold:
                matched_poiIds.add(dataframe.iloc[index]['poiId'])
    return list(matched_poiIds)

def reorder_and_extract_names(poi_list: list[dict], index_order: list[int]) -> list[str]:
    """
    Reorders the POIs based on the index_order and returns a list of names.

    :param poi_list: List of POI dictionaries, each with a "name" key.
    :param index_order: List of indices representing the desired order.
    :return: List of POI names in the new order.
    """
    return [poi_list[i]["name"] for i in index_order if i < len(poi_list)]

def extract_previous_itinerary_from_history(history: str) -> Optional[str]:
    """
    Looks through formatted chat history and returns the last known itinerary text, if present.
    """
    # Look for something that resembles an itinerary: a date line followed by times
    itinerary_match = re.search(r"\d{2}-\d{2}-\d{4}:(?:\n\s*\d{2}:\d{2} - .+)+", history)
    if itinerary_match:
        return itinerary_match.group()
    return None

def clean_and_filter_response(response_text, poi_data):
    # Step 1: Replace NaN with None in poiData
    for poi in poi_data:
        for key, value in poi.items():
            if isinstance(value, float) and math.isnan(value):
                poi[key] = None

    # Step 2: Extract POI names mentioned in the response HTML
    mentioned_pois = set(re.findall(r'>([^<]+)</a>', response_text))

    # Step 3: Filter POIs to only keep those mentioned
    filtered_pois = [poi for poi in poi_data if poi["name"] in mentioned_pois]

    return response_text, filtered_pois