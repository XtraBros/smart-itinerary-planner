import json

# ===============================
# Preference Extraction Module
# ===============================


# ---------------------------------------
# 1. Shared schema for all components
# ---------------------------------------
PREFERENCE_SCHEMA = {
    "interests": [],
    "avoid": [],
    "pace": None,
    "budget": None,
    "mobility": None,
    "time_available": None,
    "trip_intent": None
}

# ---------------------------------------
# 3. Detect if preferences are incomplete
# ---------------------------------------
def preferences_incomplete(prefs: dict) -> bool:
    """
    Define the minimum requirements for generating an itinerary.
    You can modify or expand this list as needed.
    """
    required_fields = ["interests", "time_available"]

    for field in required_fields:
        if not prefs.get(field) or prefs.get(field) in [None, "", []]:
            return True
    return False


# ---------------------------------------
# 4. Build clarification prompt for user
# ---------------------------------------
def build_preference_clarification_message():
    """
    Sends the user a structured, friendly message with examples.
    Focuses only on 'interests' and 'total available time'.
    """
    msg = """
To help me plan your itinerary efficiently, please provide a few key preferences. 
For your convenience, you can simply copy and fill the template below.

Examples of interests:
- Nature
- Museums
- Culture
- Sightseeing
- Photography
- Family-friendly attractions
- Shopping
- Art galleries
- Historic sites
- Parks & gardens

Example total available time:
- 3 hours
- Half day
- Full day

Just reply with your preferences in this format, and I’ll continue planning your itinerary!
"""
    return msg



# ---------------------------------------
# 5. Parse LLM JSON safely
# ---------------------------------------
def safe_parse_json(content: str) -> dict:
    try:
        return json.loads(content)
    except Exception:
        # return empty schema on failure
        return {k: None for k in PREFERENCE_SCHEMA}


# ---------------------------------------
# 6. Main extractor function you will call
# ---------------------------------------
def get_user_preferences(
    llm_client,
    model_name: str,
    query: str,
    chat_history: str
):
    """
    Single LLM call:
      - Extract structured preferences
      - Determine if preferences are complete
      - If complete: generate a short optimized retrieval query for POIs
      - If incomplete: provide a friendly text message asking only for missing info
    """

    SINGLE_PROMPT = f"""
You are an assistant that performs TWO tasks:

1) Extract structured travel preferences from the user's conversation.
2) If preferences are complete, generate a short optimized retrieval query for POIs.
3) If preferences are incomplete, DO NOT generate a retrieval query; instead produce a friendly message for the user asking only for missing preferences.

Return ONLY valid JSON in this structure:

{{
  "preferences": {{
    "interests": [],
    "time_available": ""
  }},
  "status": "ok" OR "need_clarification",
  "retrieval_query": "" OR null,
  "clarification_message": "" OR null
}}

Rules:
- "status" = "ok" only if enough info is present to generate an itinerary (interests + time_available).
- "status" = "need_clarification" if any required info is missing.
- If missing, produce a concise, plain-text clarification message that:
  - Provides a few example interests (Nature, Museums, Culture, Sightseeing, Photography, Family-friendly attractions, Shopping, Art galleries, Historic sites, Parks & gardens)
  - Provides example total available time (3 hours, Half day, Full day)
- Detect info already present in the user query and only ask for missing fields.

User query:
{query}

Chat history:
{chat_history}
"""

    # ------------------------------
    # Call the LLM
    # ------------------------------
    response = llm_client.chat.completions.create(
        model=model_name,
        messages=[{"role": "system", "content": SINGLE_PROMPT}]
    )

    raw = response.choices[0].message.content
    data = safe_parse_json(raw)

    # ------------------------------
    # Fill missing fields to match schema
    # ------------------------------
    prefs = data.get("preferences", {})
    for k, default in {"interests": [], "time_available": ""}.items():
        prefs.setdefault(k, default)
    data["preferences"] = prefs

    # ------------------------------
    # Enforce completeness
    # ------------------------------
    if data["status"] == "ok" and preferences_incomplete(prefs):
        # LLM said ok but preferences are incomplete → force clarification
        data["status"] = "need_clarification"
        data["retrieval_query"] = None
        data["clarification_message"] = build_preference_clarification_message()

    # ------------------------------
    # Ensure clarity: if status=need_clarification, message exists
    # ------------------------------
    if data["status"] == "need_clarification" and not data.get("clarification_message"):
        data["clarification_message"] = build_preference_clarification_message()

    return data
