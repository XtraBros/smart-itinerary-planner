class UserProfile:
    def __init__(self):
        self.data = {
            "num_people": None,
            "ages": None,
            "has_elderly": None,
            "has_children": None,
            "group_type": None,
            "trip_start_date": None,
            "trip_end_date": None,
            "total_days": None,
            "daily_hours": None,
            "interests": [],
            "pace": None,
            "budget": None,
            "mobility_needs": None,
            "dietary_restrictions": None,
            "language_preferences": None,
            "preferred_transport": None,
        }

    def is_complete(self):
        return all(value is not None and value != [] for value in self.data.values())

    def get_missing_fields(self):
        return [k for k, v in self.data.items() if v is None or v == []]

    def update(self, field, value):
        if field in self.data:
            self.data[field] = value

    def as_context(self):
        return "\n".join([f"{k.replace('_', ' ').capitalize()}: {v}" for k, v in self.data.items() if v])

