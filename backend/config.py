"""ARTHUR unified config — every part of the app reads arthur.config.json.

Priority: environment variables > arthur.config.json > built-in defaults.
"""
import json
import os

_CONFIG_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                            "arthur.config.json")

_DEFAULTS = {
    "app": "ARTHUR",
    "owner": "Mohammed Farhan",
    "api_url": "http://localhost:8000",
    "api_port": 8000,
    # Bind address for the API server. Keep 127.0.0.1 for local-only use.
    # Set to 0.0.0.0 when a physical phone needs to reach the backend over
    # your LAN — and set api_url to this machine's LAN IP, e.g.
    # "http://192.168.1.50:8000".
    "api_host": "127.0.0.1",
    "demo_mode": True,
    "cors_origins": ["http://localhost:8000", "http://localhost:8081"],
}

_file_cfg: dict = {}
try:
    with open(_CONFIG_PATH) as f:
        _file_cfg = json.load(f)
except (OSError, ValueError):
    pass


def get(key: str):
    env_map = {
        "api_url": "ARTHUR_API_URL",
        "api_port": "ARTHUR_API_PORT",
        "api_host": "ARTHUR_API_HOST",
        "demo_mode": "DEMO_MODE",
    }
    if key in env_map and env_map[key] in os.environ:
        v = os.environ[env_map[key]]
        if key == "api_port":
            return int(v)
        if key == "demo_mode":
            return v.lower() not in ("0", "false", "no")
        return v
    return _file_cfg.get(key, _DEFAULTS.get(key))
