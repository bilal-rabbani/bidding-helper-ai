"""Loads config/settings.yaml so every module reads settings the same way."""
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
SETTINGS_FILE = ROOT / "config" / "settings.yaml"


def load_settings() -> dict:
    with open(SETTINGS_FILE, encoding="utf-8") as f:
        return yaml.safe_load(f)
