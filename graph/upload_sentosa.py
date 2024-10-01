import pandas as pd
import ast
from pymongo import MongoClient
import json
import certifi

with open('../config.json' ,'r') as file:
    config = json.load(file)
# Configuration
mongo_connection_string = config['MONGO_CLUSTER_URI']
database_name = config["MONGO_DB_NAME"]
collection_name = config["DISTANCE_MATRIX"]
poi = config["POI_DB_NAME"]
events = config["EVENTS_DB_NAME"]
poi_file = "../sentosa.csv"
csv_file_path = "./distance_matrix.csv"
events_csv = "../dummy_events.csv"

# Connect to MongoDB
client = MongoClient(mongo_connection_string, tlsCAFile=certifi.where())
db = client[database_name]
collection = db[collection_name]
poidb = db[poi]
eventsdb = db[events]
# Read the CSV file into a DataFrame
distmat = pd.read_csv(csv_file_path).map(lambda x: x.strip() if isinstance(x, str) else x)

# Convert DataFrame to a list of dictionaries
data = distmat.to_dict(orient="records")

# Insert data into MongoDB
collection.delete_many({})
collection.insert_many(data)

poidf = pd.read_csv(poi_file,encoding='latin1').map(lambda x: x.strip() if isinstance(x, str) else x)
poidf['location'] = poidf['location'].apply(lambda loc: ast.literal_eval(loc))
poidf = poidf.to_dict(orient="records")


poidb.delete_many({})
poidb.insert_many(poidf)

eventsdf = pd.read_csv(events_csv, encoding='latin1').map(lambda x: x.strip() if isinstance(x, str) else x)
eventsdf = eventsdf.to_dict(orient="records")


eventsdb.delete_many({})
eventsdb.insert_many(eventsdf)

print(f"Successfully uploaded {len(data)} documents to the collection '{collection_name}', {len(eventsdf)} to {(events)} , and {len(poidf)} to '{poi} in database '{database_name}'.")
