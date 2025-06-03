from user_profile import UserProfile

QUESTION_TEMPLATES = {
    "num_people": "How many people are in your travel group?",
    "ages": "What are the ages of the group members?",
    "has_elderly": "Are there any elderly people in your group?",
    "has_children": "Are there any children in your group?",
    "group_type": "Are you traveling as a family, couple, friends, or solo?",
    "trip_start_date": "When does your trip start?",
    "trip_end_date": "When does your trip end?",
    "daily_hours": "Roughly how many hours per day do you want to spend sightseeing?",
    "interests": "What are your main interests? (e.g., nature, food, culture, shopping)",
    "pace": "Do you prefer a relaxed or packed itinerary?",
    "budget": "What is your approximate daily budget per person?",
    "mobility_needs": "Do you or anyone in the group have mobility needs or accessibility requirements?",
    "dietary_restrictions": "Any dietary restrictions we should keep in mind?",
    "language_preferences": "What languages does your group speak or prefer?",
    "preferred_transport": "Do you prefer walking, public transport, taxis, or private car?"
}

def get_next_question(profile: UserProfile):
    missing = profile.get_missing_fields()
    if not missing:
        return None
    next_field = missing[0]
    return next_field, QUESTION_TEMPLATES[next_field]