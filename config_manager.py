"""Configuration persistence for Bod RFP Compliance Checker.

Stores API key and model settings in ~/.bod/config.json.
Uses Python stdlib only — no external dependencies.
"""

import json
from pathlib import Path
from typing import Any
import os

try:
    import auth
except ImportError:
    auth = None

CONFIG_DIR = Path.home() / ".bod"
CONFIG_PATH = CONFIG_DIR / "config.json"

DEFAULT_MODEL = "gemini-3.6-flash"
DEFAULT_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai/"




def load_config() -> dict:
    """Read config from DB/env first, falling back to disk config.json."""
    config = {}
    if CONFIG_PATH.exists():
        try:
            with open(CONFIG_PATH, "r") as f:
                data = json.load(f)
            if isinstance(data, dict):
                config = data
        except (json.JSONDecodeError, OSError):
            pass

    # DB encrypted settings override file config
    if auth:
        db_key = auth.get_setting("api_key")
        db_model = auth.get_setting("model")
        db_url = auth.get_setting("base_url")
        db_rpm = auth.get_setting("rpm_limit")
        if db_key:
            config["api_key"] = db_key
        if db_model:
            config["model"] = db_model
        if db_url:
            config["base_url"] = db_url
        if db_rpm:
            config["rpm_limit"] = db_rpm

    # Environment variables override if present
    if os.environ.get("CHECKMATE_API_KEY"):
        config["api_key"] = os.environ["CHECKMATE_API_KEY"]
    if os.environ.get("CHECKMATE_MODEL"):
        config["model"] = os.environ["CHECKMATE_MODEL"]
    if os.environ.get("CHECKMATE_BASE_URL"):
        config["base_url"] = os.environ["CHECKMATE_BASE_URL"]

    return config


def save_config(config: dict) -> None:
    """Write config dict to encrypted DB and disk JSON."""
    if auth:
        for k, v in config.items():
            if v is not None:
                auth.set_setting(k, str(v))

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
    """Set a single key in config and persist."""
    config = load_config()
    config[key] = value
    save_config(config)

