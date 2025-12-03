from flask import Flask, render_template, jsonify, session
from langchain.memory import ConversationBufferWindowMemory
from helpers.RAG import RAGUnit, RAGPlatform
from helpers.model import LLMPipeline
from helpers.rpm import RetrievalPolicyManager
from backend.views import backend_bp
from api.routes import routes_bp
from auth.routes import auth_bp
import os
from helpers.config_store import (
    load_config as load_file_config,
    resolve_project_path
)
from helpers import account_store

app = Flask(__name__)
app.secret_key = os.environ.get("APP_SECRET_KEY", "dev-secret")
os.environ["TOKENIZERS_PARALLELISM"] = "false"

# Register external blueprints
app.register_blueprint(backend_bp, url_prefix="/admin")
app.register_blueprint(routes_bp)
app.register_blueprint(auth_bp, url_prefix="/auth")


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


def _default_seed_config():
    seed = load_file_config(default={})
    if seed:
        return seed
    return {
        "GPT_MODEL": "gpt-4o-mini",
        "LLM_PROVIDER": "openai",
        "MAPBOX_STYLE_URL": "mapbox://styles/mapbox/streets-v12",
        "MAP_CENTRE": "[103.8198, 1.3521]",
        "MAP_SPOTLIGHT_POLYGON": None,
        "RAG_UNITS": [
            {
                "id": "default",
                "name": "Sentosa Island",
                "description": "Sentosa POI CSV",
                "source": {"type": "csv", "path": "sentosa_with_tags.csv"},
            }
        ],
    }


def _initialize_runtime(config):
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
    if not hasattr(app, "memory"):
        app.memory = ConversationBufferWindowMemory(k=5, memory_key="history")

    app.rag = _build_rag_from_config(config)
    print("RAG loaded with units:", app.rag.list_units())
    app.rpm = RetrievalPolicyManager(app.rag)
    app.balltree, app.poi_df = app.rag.build_balltree()
    app.graph = app.rag.build_graph()
    app.session_state = {}
    app.locale_names = [unit["name"] for unit in app.rag.list_units()]
    app.locale_place_list = app.poi_df['name'].tolist()
    app.active_config = config


def _seed_accounts():
    account_store.init_db()
    active_account = account_store.get_active_account()
    if active_account:
        return active_account
    seed_config = _default_seed_config()
    default_username = os.environ.get("ADMIN_USERNAME", "admin")
    default_password = os.environ.get("ADMIN_PASSWORD", "admin123")
    account_id = account_store.create_account(
        default_username,
        default_password,
        config=seed_config,
        make_active=True
    )
    return account_store.get_account_by_id(account_id)


def reload_runtime_for_account(account_id: int):
    config = account_store.get_account_config(account_id)
    _initialize_runtime(config or {})
    app.active_account_id = account_id


app.reload_runtime_for_account = reload_runtime_for_account

active_account = _seed_accounts()
app.active_account_id = active_account["id"]
_initialize_runtime(active_account.get("config") or {})


@app.route('/')
def home():
    return render_template('index.html')


@app.route('/config', methods=['GET'])
def get_config():
    account_id = session.get("user_id") or getattr(app, "active_account_id", None)
    config = account_store.get_account_config(account_id) if account_id else app.active_config
    return jsonify({'config': config or {}})
    
if __name__ == '__main__':
    app.run(debug=True, host="0.0.0.0", port=3106)
