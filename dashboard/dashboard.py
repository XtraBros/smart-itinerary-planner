from flask import Flask, request, jsonify, render_template
import json
import pandas as pd
import io
import pymongo
from sklearn.cluster import KMeans
import requests
import time

app = Flask(__name__)

CONFIG_FILE = '../config.json'
with open(CONFIG_FILE) as json_file:
    config = json.load(json_file)
mongo = pymongo.MongoClient(config['MONGO_CLUSTER_URI'])
DB = mongo[config['MONGO_DB_NAME']]
poi_db = DB[config['POI_DB_NAME']]
df = pd.DataFrame(list(poi_db.find({}, {"_id": 0})))
required_columns = ['name', 'longitude', 'latitude', 'description']
dist_mat = DB[config["DISTANCE_MATRIX"]]
cluster_loc = DB[config['CLUSTER_LOCATIONS']]
mapbox_access_token = config['MAPBOX_ACCESS_TOKEN']

distance_matrix = pd.DataFrame(list(dist_mat.find({}, {"_id": 0})))
distance_matrix.set_index('name', inplace=True)
print(distance_matrix)
print(distance_matrix.shape)
cluster_locations = pd.DataFrame(list(cluster_loc.find({}, {"_id": 0})))

@app.route('/')
def index():
    return render_template('dashboard-index.html')

@app.route('/get-config', methods=['GET'])
def get_config():
    with open(CONFIG_FILE, 'r') as file:
        config = json.load(file)
    return jsonify(config)

@app.route('/update-config', methods=['POST'])
def update_config():
    data = request.json
    with open(CONFIG_FILE, 'w') as file:
        json.dump(data, file, indent=4)
    return jsonify({"message": "Config updated successfully"})

# Endpoint to get POI data
@app.route('/get-poi', methods=['GET'])
def get_poi():
    return df.to_json(orient='records')

@app.route('/add-poi', methods=['POST'])
def add_poi():
    new_poi = request.json
    print(f"Adding {new_poi['name']}")
    global df
    df = pd.concat([df, pd.DataFrame([new_poi])], ignore_index=True)
    add_poi_to_distance_matrix(new_poi)
    update_cluster_graph()
    document = df.loc[df['name'] == new_poi['name']].to_dict(orient='records')[0]
    # Insert the document into MongoDB
    poi_db.insert_one(document) 
    return jsonify({"message": "POI added successfully"})

@app.route('/edit-poi', methods=['POST'])
def edit_poi():
    updated_poi = request.json
    global df
    # Find the existing POI data
    existing_poi = df[df['id'] == updated_poi['id']].iloc[0]
    print(updated_poi['name'])

    # Check if longitude or latitude has changed
    location_changed = (existing_poi['longitude'] != updated_poi['longitude']) or (existing_poi['latitude'] != updated_poi['latitude'])

    # Update the DataFrame
    df.loc[df['id'] == updated_poi['id'], ['name', 'longitude', 'latitude', 'description']] = updated_poi['name'], updated_poi['longitude'], updated_poi['latitude'], updated_poi['description']

    # If location has changed, update the distance matrix and cluster graph, then update the cloud db with the full data entry.
    if location_changed:
        edit_poi_in_distance_matrix(updated_poi)
        update_cluster_graph()
    poi_db.update_one({"id": updated_poi['id']}, {"$set": updated_poi})
    return jsonify({"message": "POI updated successfully"})

@app.route('/delete-poi', methods=['POST'])
def delete_poi():
    poi_id = request.json['id']
    global df
    poi_name = df.loc[df['id'] == poi_id, 'name'].values[0]
    df = df[df['id'] != poi_id]
    poi_db.delete_one({"id": poi_id})
    delete_poi_from_distance_matrix(poi_name)
    return jsonify({"message": "POI deleted successfully"})



@app.route('/upload-csv', methods=['POST'])
def upload_csv():
    count = 0
    csv_data = request.json.get('csv')
    new_data = pd.read_csv(io.StringIO(csv_data))

    # Check if required columns are present
    missing_columns = [col for col in required_columns if col not in new_data.columns]
    if missing_columns:
        return jsonify({"message": f"Uploaded CSV is missing required columns: {', '.join(missing_columns)}"}), 400

    # Convert DataFrame to dictionary
    new_data_dict = new_data.to_dict(orient='records')

    # Check for duplicates and collect IDs and names of duplicates
    skipped_entries = []
    for poi in new_data_dict:
        if poi_db.find_one({"name": poi['name']}):
            count += 1
            skipped_entries.append({count: poi['name']})
        else:
            poi_db.insert_one(poi)

    if skipped_entries:
        message = f"CSV data uploaded successfully. Skipped entries due to duplicates: {skipped_entries}"
    else:
        message = "CSV data uploaded and merged successfully."

    return jsonify({"message": message})

#helper functions
def update_cluster_graph():
    global df
    coords = df[['latitude', 'longitude']].values
    kmeans = KMeans(n_clusters=18, random_state=0).fit(coords)
    df['cluster'] = kmeans.labels_
    cluster_locations = df[['name', 'cluster']]
    # Clear the existing collection and insert the new cluster graph
    cluster_loc.delete_many({})
    cluster_loc.insert_many(cluster_locations.to_dict(orient='records'))

def add_poi_to_distance_matrix(new_poi):
    global df, distance_matrix
    
    # Generate distances for the new POI
    new_distances = generate_distances(new_poi, df)  # This should return a list of distances
    print(f"number of distances: {len(new_distances)}")
    
    # Create new row DataFrame with correct columns
    new_row = pd.Series(new_distances, index=distance_matrix.columns, name=new_poi['name'])
    # Add new column to the existing distance matrix
    distance_matrix.loc[len(distance_matrix)] = new_row
    # Add new column
    new_column = pd.Series(new_distances + [0], index=df.index.append(pd.Index([new_poi['name']])), name=new_poi['name'])
    df[new_poi['name']] = new_column
    print(distance_matrix.shape)
        
    # Update the database
    dist_mat.delete_many({})
    dist_mat.insert_many(distance_matrix.reset_index().to_dict(orient='records'))


def delete_poi_from_distance_matrix(poi_name):
    global distance_matrix
    distance_matrix = distance_matrix.drop(index=poi_name, columns=poi_name)
    # Update the database
    dist_mat.delete_many({})
    dist_mat.insert_many(distance_matrix.to_dict(orient='records'))

def edit_poi_in_distance_matrix(updated_poi):
    global df, distance_matrix
    poi_name = df.loc[df['id'] == updated_poi['id'], 'name'].values[0]

    # Generate new distances
    new_distances = generate_distances(updated_poi, df)  # Function to calculate distances to all other POIs

    # Ensure the new distances align with the distance matrix format
    new_distances_series = pd.Series(new_distances, index=distance_matrix.columns)
    # Update the distance matrix row
    distance_matrix.loc[poi_name] = new_distances_series.drop(labels=[poi_name])
    # Update the distance matrix column
    distance_matrix[poi_name] = new_distances_series.drop(labels=[poi_name])
    # Update the database
    dist_mat.delete_many({})
    dist_mat.insert_many(distance_matrix.to_dict(orient='records'))

def generate_distances(new_poi, poi_df):
    distances = []
    new_coord = f"{new_poi['longitude']},{new_poi['latitude']}"
    for _, poi in poi_df.iterrows():
        poi_coord = f"{poi['longitude']},{poi['latitude']}"
        distance = get_distance(new_coord, poi_coord, mapbox_access_token)
        if distance is None:
            distance = 9999  # Use a large number or handle it as per your requirements
        distances.append(distance)
    print(distances)
    return distances

def get_distance(coord1, coord2, access_token, retries=3):
    url = f"https://api.mapbox.com/directions/v5/mapbox/walking/{coord1};{coord2}?geometries=geojson&steps=true&access_token={access_token}"
    for attempt in range(retries):
        response = requests.get(url)
        if response.status_code == 200:
            result = response.json()
            if 'routes' in result and len(result['routes']) > 0:
                distance = result['routes'][0]['distance']  # distance in meters
                return distance
        time.sleep(2 ** attempt)  # Exponential backoff
    return None

if __name__ == '__main__':
    app.run(debug=True, port=3000)
