from flask import Flask, render_template, jsonify
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
from helpers.config_store import (
    load_config,
    save_config,
    resolve_project_path
)

app = Flask(__name__)
os.environ["TOKENIZERS_PARALLELISM"] = "false"

# Register external blueprints
app.register_blueprint(backend_bp, url_prefix="/admin")
app.register_blueprint(routes_bp)

# Load config
config = load_config()


def _extract_llm_settings(cfg):
    llm_section = cfg.get("LLM_SETTINGS", {})
    provider = llm_section.get("provider") or cfg.get("LLM_PROVIDER") or "openai"
    model = llm_section.get("model") or cfg.get("GPT_MODEL")
    api_key = llm_section.get("api_key") or cfg.get("OPENAI_API_KEY")
    return provider or "openai", model, api_key


def _build_rag_from_config(cfg):
    rag_entries = cfg.get("RAG_UNITS") or []
    rag_units = []
    for entry in rag_entries:
        source_data = entry.get("source") or entry.get("data_source") or {}
        source_type = source_data.get("type", "csv")
        source_path = resolve_project_path(source_data.get("path"))
        if not source_path or not os.path.exists(source_path):
            continue
        rag_units.append(
            RAGUnit(
                data_source={"type": source_type, "path": source_path},
                id=entry.get("id"),
                description=entry.get("description", ""),
                name=entry.get("name", entry.get("id", "")),
            )
        )

    if not rag_units:
        default_path = resolve_project_path("sentosa_with_tags.csv")
        rag_units.append(
            RAGUnit(
                data_source={"type": "csv", "path": default_path},
                description="Sentosa POI CSV",
                name="Sentosa Island",
            )
        )
    return RAGPlatform(rag_units)

######################### LLM INIT #########################
llm_provider, llm_model, llm_api_key = _extract_llm_settings(config)
app.llm = LLMPipeline(
    provider=llm_provider,
    model=llm_model,
    api_key=llm_api_key
)
app.llm_config = {
    'persona_instructions': config.get(
        "LLM_PERSONA",
        "Speak in a Friendly & Helpful tone."
    )
}
app.memory = ConversationBufferWindowMemory(k=5, memory_key="history")

######################### RAG Data #########################
app.rag = _build_rag_from_config(config)
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

@app.route('/config', methods=['GET'])
def get_config():
    config = load_config()
    return jsonify({'config': config})
    
if __name__ == '__main__':
    app.run(debug=True, host="0.0.0.0", port=3106)
