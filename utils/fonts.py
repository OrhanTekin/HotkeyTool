"""
Bundle Geist + Geist Mono with the app and load them into the process so Tk can
address them by name without registering them system-wide.

Drop the .ttf files into assets/fonts/ — the loader picks up everything matching
Geist*.ttf and registers it with FR_PRIVATE so it's only visible to this
process. Falls back silently to system fonts if Geist files are missing.
"""
from __future__ import annotations

import ctypes
import sys
from pathlib import Path

from utils.resource_path import resource_path


_FR_PRIVATE = 0x10
_GEIST_SANS_FAMILY = "Geist"
_GEIST_MONO_FAMILY = "Geist Mono"


def load_app_fonts() -> None:
    """Load every Geist*.ttf in assets/fonts/ as a private font for this process.

    Calls ui.theme.set_font_families() with the Geist family names if at least
    one sans + one mono variant loaded, otherwise leaves the theme defaults
    (Segoe UI / Consolas) alone.
    """
    if sys.platform != "win32":
        return

    fonts_dir = resource_path("assets/fonts")
    if not fonts_dir.exists():
        return

    sans_loaded = False
    mono_loaded = False

    try:
        gdi32 = ctypes.windll.gdi32
        for ttf in sorted(fonts_dir.glob("*.ttf")):
            name = ttf.name.lower()
            ok = gdi32.AddFontResourceExW(str(ttf), _FR_PRIVATE, 0)
            if not ok:
                continue
            if "mono" in name:
                mono_loaded = True
            else:
                sans_loaded = True
    except Exception:
        return

    # Tell the theme module which family names to use. Only swap families that
    # actually loaded — if Geist Mono is missing but Geist sans is present,
    # we still upgrade the sans family.
    try:
        from ui import theme
        sans = _GEIST_SANS_FAMILY if sans_loaded else theme.font_family()
        mono = _GEIST_MONO_FAMILY if mono_loaded else theme.mono_family()
        theme.set_font_families(sans, mono)
    except Exception:
        pass


def fonts_dir_path() -> Path:
    return resource_path("assets/fonts")
