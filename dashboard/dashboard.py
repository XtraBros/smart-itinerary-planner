from flask import Flask, request, jsonify, render_template
import json
import pandas as pd
import io

app = Flask(__name__)

CONFIG_FILE = '../config.json'
POI_DATA = "../zoo-info.csv"
df = pd.read_csv(POI_DATA)
df = df.drop(columns=['id'])
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
    df.to_csv(POI_DATA, index=False)
    return jsonify({"message": "POI added successfully"})

# Endpoint to edit an existing POI
@app.route('/edit-poi', methods=['POST'])
def edit_poi():
    updated_poi = request.json
    global df
    df.loc[df['id'] == updated_poi['id'], ['name', 'longitude', 'latitude']] = updated_poi['name'], updated_poi['longitude'], updated_poi['latitude']
    df.to_csv(POI_DATA, index=False)
    return jsonify({"message": "POI updated successfully"})

# Endpoint to delete a POI
@app.route('/delete-poi', methods=['POST'])
def delete_poi():
    poi_id = request.json['id']
    df = df[df['id'] != poi_id]
    df.to_csv(POI_DATA, index=False)
    return jsonify({"message": "POI deleted successfully"})

# Endpoint to upload CSV data
@app.route('/upload-csv', methods=['POST'])
def upload_csv():
    csv_data = request.json.get('csv')
    new_data = pd.read_csv(io.StringIO(csv_data))

    # Check if required columns are present
    missing_columns = [col for col in required_columns if col not in new_data.columns]
    if missing_columns:
        return jsonify({"message": f"Uploaded CSV is missing required columns: {', '.join(missing_columns)}"}), 400

    # Identify extra columns
    extra_columns = [col for col in new_data.columns if col not in required_columns]

    # Filter out extra columns that are not present in the existing DataFrame
    existing_columns = list(df.columns)
    valid_extra_columns = [col for col in extra_columns if col in existing_columns]
    ignored_columns = [col for col in extra_columns if col not in existing_columns]

    # Ensure the new data has at least the required columns and valid extra columns
    new_data = new_data[required_columns + valid_extra_columns]

    df = pd.concat([df, new_data], ignore_index=True).drop_duplicates().reset_index(drop=True)
    df.to_csv(POI_DATA, index=False)

    message = "CSV data uploaded and merged successfully."
    if ignored_columns:
        message += f" Ignored columns: {', '.join(ignored_columns)}"

    return jsonify({"message": message})

if __name__ == '__main__':
    app.run(debug=True, port=3000)
