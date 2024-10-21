import pandas as pd
import ast
from pymongo import MongoClient
import json
import certifi

with open('config.json' ,'r') as file:
    config = json.load(file)
# Configuration
mongo_connection_string = config['MONGO_CLUSTER_URI']
database_name = config["MONGO_DB_NAME"]
profile_csv = "profile.csv"

# Connect to MongoDB
client = MongoClient(mongo_connection_string, tlsCAFile=certifi.where())
db = client[database_name]
profiledb = db["PROFILES"]

profile_df = pd.read_csv(profile_csv).map(lambda x: x.strip() if isinstance(x, str) else x)
profile_df['profile'] = profile_df['profile'].apply(lambda x: 1 if x == 0 else 0)
profile_df.to_csv(profile_csv, index = False)
# Convert DataFrame to a list of dictionaries
data = profile_df.to_dict(orient="records") 
profiledb.delete_many({})
profiledb.insert_many(data)
print("Profiles toggled")

user_profile = profiledb.find_one({"profile": 0})
print(f"using profile: {user_profile}")