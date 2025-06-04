import pandas as pd
from sklearn.feature_extraction.text import ENGLISH_STOP_WORDS
import re

# Load with encoding fallback
df = pd.read_csv("sentosa.csv", encoding='ISO-8859-1')

# Define a simple keyword extractor
def extract_keywords(text):
    if not isinstance(text, str):
        return ""
    words = re.findall(r'\b\w+\b', text.lower())
    keywords = [word for word in words if word not in ENGLISH_STOP_WORDS and len(word) > 3]
    return ", ".join(sorted(set(keywords)))

# Apply to description column (adjust this if the column name differs)
df["relevant_tags"] = df["description"].apply(extract_keywords)

# Save to new file
df.to_csv("sentosa_with_tags.csv", index=False)
