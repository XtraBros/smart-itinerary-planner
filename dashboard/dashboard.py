from flask import Flask, request, jsonify, render_template
import json
import pandas as pd
import io
import pymongo

app = Flask(__name__)

CONFIG_FILE = '../config.json'
with open(CONFIG_FILE) as json_file:
    config = json.load(json_file)
mongo = pymongo.MongoClient(config['MONGO_CLUSTER_URI'])
DB = mongo[config['MONGO_DB_NAME']]
poi_db = DB[config['POI_DB_NAME']]
df = pd.DataFrame(list(poi_db.find({}, {"_id": 0})))
df = df.drop(columns=["id"])
required_columns = ['name', 'longitude', 'latitude', 'description']

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

# Endpoint to add a new POI
@app.route('/add-poi', methods=['POST'])
def add_poi():
    new_poi = request.json
    global df
    new_poi['id'] = max(df['id']) + 1 if not df.empty else 1
    df = df.append(new_poi, ignore_index=True)
    poi_db.insert_one(new_poi)
    return jsonify({"message": "POI added successfully"})

# Endpoint to edit an existing POI
@app.route('/edit-poi', methods=['POST'])
def edit_poi():
    updated_poi = request.json
    global df
    df.loc[df['id'] == updated_poi['id'], ['name', 'longitude', 'latitude', 'description']] = updated_poi['name'], updated_poi['longitude'], updated_poi['latitude'], updated_poi['description']
    poi_db.update_one({"id": updated_poi['id']}, {"$set": updated_poi})
    return jsonify({"message": "POI updated successfully"})

# Endpoint to delete a POI
@app.route('/delete-poi', methods=['POST'])
def delete_poi():
    poi_id = request.json['id']
    global df
    df = df[df['id'] != poi_id]
    poi_db.delete_one({"id": poi_id})
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

if __name__ == '__main__':
    app.run(debug=True, port=3000)
