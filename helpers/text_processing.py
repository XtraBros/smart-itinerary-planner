import re
from rapidfuzz import process, fuzz
import json

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


def insertHyperlinks(message, replacements):
    # Split the message into chunks by the `~` delimiter
    chunks = message.split("~")
    # Replace chunks with hyperlinks where applicable
    chunks = map(lambda chunk: replacements.get(chunk.strip(), chunk), chunks)
    # Reconstruct the message by joining the mapped chunks
    final_message = "".join(chunks)
    # Step 1: Process numbered and bulleted lists
    final_message = format_paragraphs(final_message)
    return final_message

def format_paragraphs(text):
    # Split text into paragraphs by double line breaks
    paragraphs = text.split('\n\n')
    # Wrap each paragraph in <p> tags and join them
    formatted_text = ''.join([f'<p>{p.strip()}</p>' for p in paragraphs])
    # Replace single line breaks with <br> for line breaks within a paragraph
    formatted_text = formatted_text.replace('\n', '<br>')
    return formatted_text

def process_formatted_history(history):
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
    
    # Iterate through the names to match
    for input_name in names:
        # Find the best matches for the current input_name in the dataframe
        results = process.extract(
            input_name,
            dataframe['name'],
            scorer=fuzz.ratio,
            limit=None
        )
        
        # Filter matches that meet the similarity threshold
        for match_name, score, index in results:
            if score >= threshold:
                matched_poiIds.add(dataframe.iloc[index]['poiId'])
    
    return list(matched_poiIds)