from flask import Flask, request, jsonify, render_template
import json
import pandas as pd
import io
import pymongo
from sklearn.cluster import KMeans
import requests
import time
import certifi
from google.cloud import storage
import os

app = Flask(__name__)

CONFIG_FILE = '../config.json'
with open(CONFIG_FILE) as json_file:
    config = json.load(json_file)
mongo = pymongo.MongoClient(config['MONGO_CLUSTER_URI'],tlsCAFile=certifi.where())
print("Successfully cononected to Database.")
DB = mongo[config['MONGO_DB_NAME']]
poi_db = DB[config['POI_DB_NAME']]
poi_df = pd.DataFrame(list(poi_db.find({}, {"_id": 0})))
print(f"Loaded {len(poi_df)} POIs.")
change_log = {}
required_columns = ['name', 'longitude', 'latitude', 'description', 'location']
dist_mat_db = DB[config["DISTANCE_MATRIX"]]
mapbox_access_token = config['MAPBOX_ACCESS_TOKEN']
distance_matrix = pd.DataFrame(list(dist_mat_db.find({}, {"_id": 0})))
distance_matrix.set_index('name', inplace=True)
# Initialize the Google Cloud Storage client



@app.route('/')
def index():
    return render_template('dashboard-index.html')

@app.route('/get_config', methods=['GET'])
def get_config():
    with open(CONFIG_FILE, 'r') as file:
        config = json.load(file)
    return jsonify(config)

@app.route('/update_config', methods=['POST'])
def update_config():
    data = request.json
    config_file_path = CONFIG_FILE  # Assuming CONFIG_FILE is the path to your config file
    app_file_path = "../app.py"  # Replace with the actual path to your app.py

    # Write the new config data
    with open(config_file_path, 'w') as file:
        json.dump(data, file, indent=4)

    # "Touch" the app.py file to update its modified timestamp
    touch_file(app_file_path)

    return jsonify({"message": "Config updated successfully"})

def touch_file(filepath):
    """ Update the modified time of the file to trigger a Flask reload """
    with open(filepath, 'a'):
        os.utime(filepath, None)

# Endpoint to get POI data
@app.route('/get_poi', methods=['GET'])
def get_poi():
    return poi_df.to_json(orient='records')

@app.route('/add_poi', methods=['POST'])
def add_poi():
    new_poi = request.json
    print(f"Adding {new_poi['name']}")
    global poi_df 
    if new_poi['name'] in poi_df['name'].values:
        return jsonify({"message": f"POI with name '{new_poi['name']}' already exists"}), 400
    if 'longitude' in new_poi and 'latitude' in new_poi:
        new_poi['location'] = [float(new_poi['longitude']), float(new_poi['latitude'])]
    if 'target_audience' in new_poi:
        new_poi['for'] = new_poi.pop('target_audience')
    new_poi['id'] = len(poi_df)
    print(new_poi)
    poi_df = pd.concat([poi_df, pd.DataFrame([new_poi])], ignore_index=True)
    add_poi_to_distance_matrix(new_poi)
    # update change log
    update_change_log("add", False, new_poi['name'])
    return jsonify({"message": "POI added successfully"})

@app.route('/edit_poi', methods=['POST'])
def edit_poi():
    updated_poi = request.json  # Receive data as a single POI from the form
    global poi_df, distance_matrix

    # Extract values from the request (updated POI)
    poi_id = int(updated_poi.get('id'))  # Use a unique ID to find the POI
    print(f"===Editting POI ID: {poi_id}===")
    updated_name = updated_poi['name']
    updated_longitude = float(updated_poi['longitude'])
    updated_latitude = float(updated_poi['latitude'])
    updated_description = updated_poi['description']
    updated_category = updated_poi['category']
    updated_target_audience = updated_poi['target_audience']
    updated_operating_hours = updated_poi['operating_hours']

    # Check if the POI exists in the DataFrame using the ID
    existing_poi = poi_df.loc[poi_df['id'] == poi_id]
    if existing_poi.empty:
        return jsonify({"error": "POI not found"}), 404

    # Convert the existing POI row to a dictionary for comparison
    existing_poi = existing_poi.iloc[0].to_dict()

    # Check if the POI name has changed
    name_changed = (existing_poi['name'] != updated_name)

    # Check if the location (longitude or latitude) has changed
    location_changed = (
        float(existing_poi['longitude']) != float(updated_longitude) or 
        float(existing_poi['latitude']) != float(updated_latitude)
    )

    # Update the POI details in the DataFrame
    poi_df.loc[poi_df['id'] == poi_id, 'name'] = updated_name
    poi_df.loc[poi_df['id'] == poi_id, 'longitude'] = updated_longitude
    poi_df.loc[poi_df['id'] == poi_id, 'latitude'] = updated_latitude
    poi_df.loc[poi_df['id'] == poi_id, 'description'] = updated_description
    poi_df.loc[poi_df['id'] == poi_id, 'category'] = updated_category
    poi_df.loc[poi_df['id'] == poi_id, 'target_audience'] = updated_target_audience
    poi_df.loc[poi_df['id'] == poi_id, 'operating_hours'] = updated_operating_hours

    # Handle name change in the distance matrix if necessary
    if name_changed:
        old_name = existing_poi['name']
        distance_matrix = distance_matrix.rename(index={old_name: updated_name}, columns={old_name: updated_name})
        # rename thumbnail:

        print(f"Name change detected: Old Name '{old_name}' -> New Name '{updated_name}'")
        update_change_log('edit', old_name, updated_name)
    else:
        update_change_log('edit', False, updated_name)

    # Handle location change in the distance matrix
    if location_changed:
        edit_poi_in_distance_matrix(updated_poi, existing_poi)
        print(f"Location change detected for {updated_name}: Old [{existing_poi['longitude']}, {existing_poi['latitude']}] -> New [{updated_longitude}, {updated_latitude}]")
    return jsonify({"message": f"POI {updated_name} updated successfully"}), 200

# delete pois
@app.route('/delete_poi', methods=['POST'])
def delete_poi():
    poi_id = int(request.json['id'])
    global poi_df
    poi_name = poi_df.loc[poi_df['id'] == poi_id, 'name'].iloc[0]
    print(f"Deleting {poi_id}: {poi_name}")
    poi_df = poi_df.drop(poi_id, axis=0)
    delete_poi_from_distance_matrix(poi_name)
    poi_df = poi_df.reset_index()
    update_change_log('delete',False,poi_name)
    return jsonify({"message": f"POI {poi_name} deleted successfully"}), 200


@app.route('/upload_csv', methods=['POST'])
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

@app.route('/view_changes', methods=['POST'])
def view_changes():
    return jsonify(change_log)

@app.route('/commit_changes', methods=['POST'])
def commit_changes():
    global change_log, poi_df, poi_db, distance_matrix, dist_mat_db
    num_changes = len(change_log)
    # Process changes based on operation type
    for change_id, change in change_log.items():
        operation = change.get('operation')
        name = change.get('name')
        renamed = change.get('renamed_from')
        formatted_new_name = f"{name.lower().replace(' ', '-')}.jpg"

        if operation == 'edit' and renamed:
            # For edit operation, rename the thumbnail in the Google Cloud Storage bucket
            formatted_old_name = f"{renamed.lower().replace(' ', '-')}.jpg"
            try:
                rename_thumbnail(formatted_old_name, formatted_new_name)
            except Exception as e:
                print(f"Error renaming thumbnail: {e}")

        elif operation == 'delete':
            # For delete operation, remove the thumbnail from the Google Cloud Storage bucket
            try:
                delete_thumbnail(formatted_new_name)
            except Exception as e:
                print(f"Error deleting thumbnail: {e}")
    # Clear the existing and upload new POI data in the database
    poi_db.delete_many({})  # Empty the poi_db collection
    poi_db.insert_many(poi_df.to_dict('records'))

    # Reset index of distance matrix
    distance_matrix.reset_index(inplace=True)
    # Clear the existing distance matrix data in the database and upload new data.
    dist_mat_db.delete_many({})  # Empty the dist_mat_db collection
    dist_mat_db.insert_many(distance_matrix.to_dict('records'))
    # set index of distance matrix
    distance_matrix.set_index('name', inplace=True)

    # Empty change logs:
    change_log = {}
    return jsonify({"message": f"Committed {num_changes} changes to the database"})

# @app.route('/upload_thumbnail', methods=['POST'])
# def upload_thumbnail():
#     if 'thumbnail' not in request.files or 'fileName' not in request.form:
#         return jsonify({"error": "No file or filename provided"}), 400

#     file = request.files['thumbnail']
#     file_name = request.form['fileName']

#     try:
#         # Set the destination path within the bucket (folder)
#         destination_blob_name = f"{folder_name}/{file_name}"
#         blob = bucket.blob(destination_blob_name)

#         # Upload the file
#         blob.upload_from_file(file.stream, content_type='image/jpeg')

#         return jsonify({"message": f"Thumbnail {file_name} uploaded successfully"}), 200
#     except Exception as e:
#         return jsonify({"error": str(e)}), 500

####################################################################################################################################
####################################################################################################################################
# helper functions
def update_cluster_graph():
    global poi_df
    coords = df[['latitude', 'longitude']].values

    # Fit KMeans model
    kmeans = KMeans(n_clusters=18, random_state=0).fit(coords)
    df['cluster'] = kmeans.labels_

    # Prepare centroid locations data
    centroids = kmeans.cluster_centers_
    centroid_data = [{
        "cluster": i,
        "latitude": centroid[0],
        "longitude": centroid[1]
    } for i, centroid in enumerate(centroids)]

    # Clear the existing centroid collection and insert the new centroid data
    # cluster_loc.delete_many({})
    # cluster_loc.insert_many(centroid_data)

    # print("Cluster graph and centroids updated successfully.")

def add_poi_to_distance_matrix(new_poi):
    global poi_df, distance_matrix

    poi_name = new_poi['name'].replace('[', '').replace(']', '').replace("'", '')
    # Generate distances for the new POI
    new_distances = generate_distances(new_poi, poi_df)  # This should return a list of distances including the distance to itself

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


def delete_poi_from_distance_matrix(poi_name):
    poi_name = poi_name.replace('[', '').replace(']', '').replace("'", '')
    global distance_matrix
    distance_matrix = distance_matrix.drop(index=poi_name, columns=poi_name)

def edit_poi_in_distance_matrix(updated_poi, existing_poi):
    global poi_df, distance_matrix
    curr_poi_name = existing_poi['name']
    new_poi_name = updated_poi['name']

    # Generate new distances
    new_distances = generate_distances(updated_poi, poi_df)  # Function to calculate distances to all other POIs
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
    # update_cluster_graph()

    # Perform a single batch upload to MongoDB
    if new_documents:
        poi_db.insert_many(new_documents)

# Function to update the change log with a new entry
def update_change_log(operation, renamed_from, name):
    # Generate a new integer key for the next entry in the change log
    # This key will be the next integer after the current maximum key
    if change_log:
        new_id = max(change_log.keys()) + 1
    else:
        new_id = 1  # Start with key 1 if change_log is empty

    # Create a new log entry with the 'operation' and 'name'
    change_log[new_id] = {
        'operation': operation,
        'name': name,
        'renamed_from': renamed_from 
    }
    print(f"{operation} operation on {name} recorded.")

def rename_thumbnail(old_name, new_name):
    global bucket
    """Renames a file in a Google Cloud Storage bucket."""
    old_blob = bucket.blob(old_name)
    new_blob = bucket.blob(new_name)

    # Copy the blob to a new name
    new_blob.rewrite(old_blob)
    
    # Delete the old blob
    old_blob.delete()

    print(f"Renamed file {old_name} to {new_name}")

def delete_thumbnail(file_name):
    """Deletes a file from a Google Cloud Storage bucket."""
    global bucket
    blob = bucket.blob(file_name)

    # Delete the blob
    blob.delete()

    print(f"Deleted file {file_name}")

if __name__ == '__main__':
    app.run(debug=True, host="127.0.0.1", port=3000)
