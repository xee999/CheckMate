"""Configuration persistence for Bod RFP Compliance Checker.

Stores API key and model settings in ~/.bod/config.json.
Uses Python stdlib only — no external dependencies.
"""

import json
from pathlib import Path
from typing import Any

CONFIG_DIR = Path.home() / ".bod"
CONFIG_PATH = CONFIG_DIR / "config.json"

DEFAULT_MODEL = "opencode/deepseek-v4-flash-free"
DEFAULT_BASE_URL = "https://opencode.ai/zen/v1"


def load_config() -> dict:
    """Read config file and return as dict.

    Returns empty dict if the file is missing, unreadable, or contains
    invalid JSON.
    """
    if not CONFIG_PATH.exists():
        return {}

    try:
        with open(CONFIG_PATH, "r") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            return {}
        return data
    except (json.JSONDecodeError, OSError):
        return {}


def save_config(config: dict) -> None:
    """Write config dict to disk as pretty JSON.

    Creates ~/.bod/ directory if it does not exist.
    """
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    with open(CONFIG_PATH, "w") as f:
        json.dump(config, f, indent=2)
        f.write("\n")


def is_configured() -> bool:
    """Return True if a non-empty api_key is present in config."""
    config = load_config()
    key = config.get("api_key", "")
    return bool(key)


def get(key: str, default: Any = None) -> Any:
    """Read a single key from config, returning *default* if absent."""
    config = load_config()
    return config.get(key, default)


def set(key: str, value: Any) -> None:
    """Set a single key in config and persist to disk."""
    config = load_config()
    config[key] = value
    save_config(config)
