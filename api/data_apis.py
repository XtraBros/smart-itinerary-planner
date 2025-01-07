import requests
import random

def sample_pois(pois, sample_size):
    """
    Randomly samples a specified number of POIs from the filtered list.
    
    Parameters:
    - pois: List of POI dictionaries.
    - sample_size: Number of POIs to sample.
    
    Returns:
    - List of sampled POIs.
    """
    if len(pois) <= sample_size:
        return pois  # Return all POIs if the sample size exceeds available POIs
    return random.sample(pois, sample_size)

def get_poi_data(api_url,uid):
    """
    Fetch data from the API using the given uid.

    Parameters:
        uid (str): The unique identifier for the place.

    Returns:
        dict: The response data from the API.
    """
    try:
        api_url = f"{api_url}" + f"/{uid}"
        # Make the GET request to the API
        response = requests.get(api_url)

        # Raise an exception for HTTP errors
        response.raise_for_status()

        # Parse and return the 'data' field from the response JSON
        response_json = response.json()
        return response_json.get("data", {})

    except requests.RequestException as e:
        return {"error": str(e)}

def get_poi_description(api_url,uid):
    """
    Fetch the description from the API using the given uid.

    Parameters:
        uid (str): The unique identifier for the place.

    Returns:
        str: The description of the place or an error message.
    """
    try:
        api_url = f"{api_url}" + f"/{uid}"
        # Make the GET request to the API
        response = requests.get(api_url)

        # Raise an exception for HTTP errors
        response.raise_for_status()

        # Parse and return the 'data' field from the response JSON
        response_json = response.json()
        data = response_json.get("data", {})
        return data.get("description", "No description available")

    except requests.RequestException as e:
        return {"error": str(e)}
    
def call_api(url, payload):
    """
    Calls an API with the given URL and payload.

    Args:
        url (str): The endpoint URL to send the request to.
        payload (dict): A dictionary of parameters to send with the request.

    Returns:
        dict: The API response parsed as JSON.
    """
    try:
        # Make the API request
        response = requests.get(url, params=payload)
        
        # Raise an error if the request was unsuccessful
        response.raise_for_status()
        
        # Parse and return the JSON response
        return response.json()
    except requests.exceptions.RequestException as e:
        # Handle exceptions, such as network errors
        print(f"An error occurred: {e}")
        return None