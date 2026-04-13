import sys
from pathlib import Path


def resource_path(relative: str) -> Path:
    """Resolve path to a bundled asset. Works for dev and PyInstaller frozen."""
    base = getattr(sys, "_MEIPASS", None)
    if base:
        return Path(base) / relative
    return Path(__file__).parent.parent / relative
