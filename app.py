from flask import Flask, render_template, jsonify, request
import json
import random
import numpy as np
from langchain.memory import ConversationBufferWindowMemory
from helpers.RAG import RAGUnit, RAGPlatform
from helpers.model import LLMPipeline
from helpers.route_solver import get_distance_from_poi
from helpers.rpm import RetrievalPolicyManager
from backend.views import backend_bp
from api.routes import routes_bp
import os

CONFIG_FILE = 'config.json'

app = Flask(__name__)
os.environ["TOKENIZERS_PARALLELISM"] = "false"

# Register external blueprints
app.register_blueprint(backend_bp, url_prefix="/admin")
app.register_blueprint(routes_bp)

# Load config
with open(CONFIG_FILE, 'r') as file:
    config = json.load(file)

######################### LLM INIT #########################
app.llm = LLMPipeline(
    provider='openai',
    model=config['GPT_MODEL'],
    api_key=config['OPENAI_API_KEY']
)
app.llm_config = {'persona_instructions':"Speak in a Friendly & Helpful tone."}
app.memory = ConversationBufferWindowMemory(k=5, memory_key="history")

######################### RAG Data #########################
unit = RAGUnit(
    data_source={"type": "csv", "path": "./sentosa_with_tags.csv"},
    description="Sentosa POI CSV",
    name="Sentosa Island"
)
app.rag = RAGPlatform([unit])
print("RAG loaded with units:", app.rag.list_units())
app.rpm = RetrievalPolicyManager(app.rag)
app.balltree, app.poi_df = app.rag.build_balltree()
app.graph = app.rag.build_graph()
app.session_state = {}
# poi_df['clicks'] = [random.randint(1, 100) for _ in range(len(poi_df))]

######################### Misc Init #########################
app.locale_names = [unit["name"] for unit in app.rag.list_units()]
app.locale_place_list = app.poi_df['name'].tolist()

@app.route('/')
def home():
    return render_template('index.html')

def load_config():
    with open(CONFIG_FILE) as f:
        return json.load(f)

def save_config(data):
    with open(CONFIG_FILE, 'w') as f:
        json.dump(data, f, indent=2)

@app.route('/config', methods=['GET'])
def get_config():
    config = load_config()
    return jsonify({'config': config})
    
if __name__ == '__main__':
    app.run(debug=True, host="0.0.0.0", port=3106)
