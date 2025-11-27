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

def fix_broken_initialisms(text):
    """
    Fix cases like:
        S.E.A.\nAquarium  →  S.E.A. Aquarium
        U.S.A. <br> Pavilion  →  U.S.A. Pavilion
    """
    return re.sub(
        r'([A-Z](?:\.[A-Z])+\.)(?:\s*|\s*<br\s*/?>\s*|\n+)(?=[A-Z][a-z])',
        r'\1 ',
        text
    )

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
    # Sort longer names first
    sorted_names = sorted(poi_names, key=len, reverse=True)

    for name in sorted_names:
        pattern = re.compile(
            r'\b' + re.escape(name) + r'\b',
            flags=re.IGNORECASE
        )

        def replacer(match):
            # Use the *original* POI name in the marker
            return f"~{name}~"

        text = pattern.sub(replacer, text)

    return text


def extract_poi_names_and_coords(poi_data):
    names = []
    coordinates = []
    for poi in poi_data:
        names.append(poi["name"])
        coordinates.append((poi["longitude"], poi["latitude"]))
    return names, coordinates

def hyperlink_pois_in_response(response_text, poi_data):
    # 1. Fix initialisms BEFORE processing anything
    cleaned_text = fix_broken_initialisms(response_text)

    # 2. Extract names + coords
    names, coords = extract_poi_names_and_coords(poi_data)

    # 3. Build hyperlink dictionary
    hyperlinks = create_hyperlinks(names, coords)

    # 4. Mark POI names
    marked_text = mark_poi_names(cleaned_text, names)

    # 5. Replace marked POIs with hyperlinks and format output
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
    """
    Converts LangChain memory history (string or dict) into a clean,
    LLM-friendly format like:

    [User] ...
    [Assistant] ...
    """

    # If history passed as {"history": "..."} unwrap it
    if isinstance(history, dict) and "history" in history:
        history = history["history"]

    if not isinstance(history, str):
        return ""  # safely fallback

    lines = history.strip().split("\n")
    cleaned = []

    for line in lines:
        # Normalize human messages
        if line.startswith("Human:") or line.startswith("User:"):
            content = line.split(":", 1)[1].strip()
            cleaned.append(f"[User] {content}")
            continue

        # Normalize assistant messages
        if line.startswith("AI:"):
            raw = line[3:].strip()

            # Try to parse {"response": "..."}
            try:
                data = json.loads(raw)
                content = data.get("response", raw)
            except Exception:
                content = raw

            cleaned.append(f"[Assistant] {content}")
            continue

        # Other (unexpected) lines → include as-is
        cleaned.append(line)

    return "\n".join(cleaned)


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


def detect_nearby_intent(query: str, threshold: int = 80) -> bool:
    q = query.lower()
    NEARBY_KEYWORDS = ["nearby", "closest", "around me", "near me", "near by"]
    # split into words/phrases
    tokens = q.split()
    for token in tokens:
        for kw in NEARBY_KEYWORDS:
            score = fuzz.ratio(token, kw)  # 0-100
            if score >= threshold:
                return True
    # also check multi-word patterns
    for kw in NEARBY_KEYWORDS:
        score = fuzz.ratio(q, kw)
        if score >= threshold:
            return True
    return False

def normalize_name(name: str) -> str:
    if not name:
        return ""
    name = name.strip().lower()
    # Remove punctuation except spaces and letters/numbers
    name = re.sub(r"[^\w\s]", "", name)
    # Collapse multiple spaces
    name = re.sub(r"\s+", " ", name)
    return name

def chunk_text(text, max_len=400):
    """
    Yield text chunks suitable for streaming.
    - Keeps paragraph boundaries by splitting on double-newline.
    - If a paragraph exceeds max_len, split it into contiguous slices.
    - Preserves whitespace and markdown formatting.
    """
    if not text:
        return
    paragraphs = text.split("\n\n")  # preserve paragraphs

    for i, p in enumerate(paragraphs):
        if p == "":
            # keep explicit blank paragraph
            yield "\n\n"
            continue

        # keep original paragraph content (do NOT strip)
        # but re-add delimiter so downstream renderer gets paragraph breaks
        paragraph_with_break = p
        # If paragraph is small enough, emit it with paragraph break (except maybe last)
        if len(paragraph_with_break) <= max_len:
            # add the paragraph separator back (so markdown headers/lists are recognized)
            yield paragraph_with_break + ("\n\n" if i != len(paragraphs) - 1 else "")
        else:
            # split long paragraph into sliding slices (preserve order, no trimming)
            start = 0
            while start < len(paragraph_with_break):
                end = min(start + max_len, len(paragraph_with_break))
                slice_ = paragraph_with_break[start:end]
                # If not the last slice of the paragraph, don't append the paragraph break.
                if end < len(paragraph_with_break):
                    yield slice_
                else:
                    # last slice of the paragraph: re-add paragraph break if it's not the final paragraph
                    yield slice_ + ("\n\n" if i != len(paragraphs) - 1 else "")
                start = end
