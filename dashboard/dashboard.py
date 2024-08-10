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
print("Successfully cononected to Database.")
DB = mongo[config['MONGO_DB_NAME']]
poi_db = DB[config['POI_DB_NAME']]
df = pd.DataFrame(list(poi_db.find({}, {"_id": 0})))
required_columns = ['name', 'longitude', 'latitude', 'description']
dist_mat = DB[config["DISTANCE_MATRIX"]]
cluster_loc = DB[config['CLUSTER_LOCATIONS']]
mapbox_access_token = config['MAPBOX_ACCESS_TOKEN']

distance_matrix = pd.DataFrame(list(dist_mat.find({}, {"_id": 0})))
distance_matrix.set_index('name', inplace=True)
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
    updated_pois = request.json
    global df, distance_matrix

    # Convert the updated POIs list to a DataFrame
    updated_df = pd.DataFrame(updated_pois)[:len(df)]
    updated_df.index = range(len(updated_df))
    print(df)
    print(updated_df)
    # Ensure the indices and columns of the updated_df match those of df
    updated_df = updated_df.reindex(columns=df.columns)

    # Find the POIs that have changed
    changed_pois = updated_df.compare(df)
    
    # Update the DataFrame
    for index in changed_pois.index:
        updated_values = updated_df.loc[index].to_dict()
        
        # Check if longitude or latitude has changed
        existing_poi = df.loc[index]
        location_changed = (existing_poi['longitude'] != updated_values['longitude']) or (existing_poi['latitude'] != updated_values['latitude'])
        name_changed = (existing_poi['name'] != updated_values['name'])
        # Update the DataFrame row
        for col, val in updated_values.items():
            df.at[index, col] = val
        if name_changed:
            old_name = existing_poi['name']
            new_name = updated_values['name']
        
            distance_matrix = distance_matrix.rename(index={old_name: new_name}, columns={old_name: new_name})        # If location has changed, update the distance matrix and cluster graph
        if location_changed:
            edit_poi_in_distance_matrix(updated_values, existing_poi)
            update_cluster_graph()

        # Update the cloud database with the full data entry
        poi_db.update_one({"id": index}, {"$set": updated_values})
    
    return jsonify({"message": "POIs updated successfully"})

# delete pois
@app.route('/delete-poi', methods=['POST'])
def delete_poi():
    deleted_rows = request.json
    print(deleted_rows)
    global df

    for row in deleted_rows:
        poi_id = row['id']
        poi_name = row['name']
        print(poi_name)
        df = df.drop(poi_id, axis=0)
        poi_db.delete_one({"name": poi_name})
        delete_poi_from_distance_matrix(poi_name)
    df = df.reset_index()
    return jsonify({"success": True}), 200


@app.route('/upload-csv', methods=['POST'])
def upload_csv():
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
            skipped_entries.append(poi['name'])
        else:
            poi_db.insert_one(poi)

    # Add new POIs to the global DataFrame and update distance matrix and cluster graph
    add_multiple_pois(new_data[~new_data['name'].isin(skipped_entries)])

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
    
    poi_name = new_poi['name'].replace('[', '').replace(']', '').replace("'", '')
    # Generate distances for the new POI
    new_distances = generate_distances(new_poi, df)  # This should return a list of distances including the distance to itself

    # Ensure the length of new_distances matches the expected length
    if len(new_distances) != len(distance_matrix) + 1:
        raise ValueError("The length of new_distances must be one more than the number of rows/columns in distance_matrix.")

    # Append the new POI's name to the index
    new_index = distance_matrix.columns.tolist() + [poi_name]

    # Add new row to the distance matrix
    distance_matrix.loc[poi_name] = new_distances[:-1]

    # Add new column to the distance matrix
    new_column = pd.Series(new_distances, index=new_index, name=poi_name)
    distance_matrix[poi_name] = new_column
    # Update the database
    dist_mat.delete_many({})
    dist_mat.insert_many(distance_matrix.reset_index().to_dict(orient='records'))


def delete_poi_from_distance_matrix(poi_name):
    poi_name = poi_name.replace('[', '').replace(']', '').replace("'", '')
    global distance_matrix
    distance_matrix = distance_matrix.drop(index=poi_name, columns=poi_name)
    # Update the database
    dist_mat.delete_many({})
    dist_mat.insert_many(distance_matrix.reset_index().to_dict(orient='records'))


def edit_poi_in_distance_matrix(updated_poi, existing_poi):
    global df, distance_matrix
    curr_poi_name = existing_poi['name']
    new_poi_name = updated_poi['name']
    
    # Generate new distances
    new_distances = generate_distances(updated_poi, df)  # Function to calculate distances to all other POIs
    print(new_distances)
    
    # Ensure the new distances align with the distance matrix format
    if len(new_distances) != len(distance_matrix):
        print(new_distances)
        print(f'length: {len(new_distances)}')
        print(f'needed: {len(distance_matrix)}')

        raise ValueError("The length of new_distances must match the number of rows/columns in distance_matrix.")
    
    new_distances_series = pd.Series(new_distances, index=distance_matrix.columns)
    
    # Rename the POI in the index if necessary
    if curr_poi_name != new_poi_name:
        distance_matrix.rename(index={curr_poi_name: new_poi_name}, columns={curr_poi_name: new_poi_name}, inplace=True)
    
    # Update the distance matrix row
    distance_matrix.loc[new_poi_name] = new_distances_series
    
    # Update the distance matrix column
    distance_matrix[new_poi_name] = new_distances_series
    print(distance_matrix)
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

def add_multiple_pois(df_new_pois):
    global df
    new_documents = []
    for index, new_poi in df_new_pois.iterrows():
        print(f"Adding {new_poi['name']}")
        df = pd.concat([df, pd.DataFrame([new_poi])], ignore_index=True)
        add_poi_to_distance_matrix(new_poi)
        document = df.loc[df['name'] == new_poi['name']].to_dict(orient='records')[0]
        new_documents.append(document)
    
    # Update the cluster graph after adding all POIs
    update_cluster_graph()
    
    # Perform a single batch upload to MongoDB
    if new_documents:
        poi_db.insert_many(new_documents)

if __name__ == '__main__':
    app.run(debug=True, port=3000)
