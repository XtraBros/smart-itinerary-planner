import json
import os
from threading import Lock


PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
CONFIG_PATH = os.path.join(PROJECT_ROOT, "config.json")
_config_lock = Lock()


def load_config():
    with _config_lock:
        with open(CONFIG_PATH, "r") as cfg:
            return json.load(cfg)


def save_config(data):
    with _config_lock:
        with open(CONFIG_PATH, "w") as cfg:
            json.dump(data, cfg, indent=2)


def resolve_project_path(path_value):
    if not path_value:
        return ""
    if os.path.isabs(path_value):
        return path_value
    return os.path.abspath(os.path.join(PROJECT_ROOT, path_value))


def project_relative_path(path_value):
    if not path_value:
        return ""
    abs_path = os.path.abspath(path_value)
    if abs_path.startswith(PROJECT_ROOT):
        return os.path.relpath(abs_path, PROJECT_ROOT)
    return abs_path
