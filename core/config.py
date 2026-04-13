import json
import os
from pathlib import Path

from core.models import AppConfig

CONFIG_DIR = Path(os.environ.get("APPDATA", Path.home())) / "HotkeyTool"
CONFIG_PATH = CONFIG_DIR / "config.json"


def load_config() -> AppConfig:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    if not CONFIG_PATH.exists():
        return AppConfig()
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            raw = json.load(f)
        raw = _migrate(raw)
        return AppConfig.from_dict(raw)
    except Exception:
        return AppConfig()


def save_config(config: AppConfig) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    tmp = CONFIG_PATH.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(config.to_dict(), f, indent=2, ensure_ascii=False)
    os.replace(tmp, CONFIG_PATH)


def export_config(config: AppConfig, path: Path) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(config.to_dict(), f, indent=2, ensure_ascii=False)


def import_config(path: Path) -> AppConfig:
    with open(path, "r", encoding="utf-8") as f:
        raw = json.load(f)
    raw = _migrate(raw)
    return AppConfig.from_dict(raw)


def _migrate(raw: dict) -> dict:
    version = raw.get("version", 1)
    if version < 2:
        raw.setdefault("settings", {})
        raw["version"] = 2
    return raw
