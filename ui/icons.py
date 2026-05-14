"""
Static icon + brand-logo loader.

All glyphs live as monochrome (white-on-transparent) PNGs in
`assets/icons/`.  `icon(name, size, color)` opens the master PNG once,
replaces its RGB channel with the requested tint (preserving the alpha
channel so anti-aliased edges stay smooth), resizes, and returns a
CTkImage.  Result is cached.
"""
from __future__ import annotations

from functools import lru_cache
from typing import Tuple

import customtkinter as ctk
from PIL import Image

from ui import theme


def _hex_to_rgb(c: str) -> Tuple[int, int, int]:
    c = c.lstrip("#")
    return int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16)


# ── Brand logo (static PNG asset) ──────────────────────────────────────────────

@lru_cache(maxsize=4)
def brand_logo(size: int = 30) -> ctk.CTkImage:
    """Return the brand logo at the requested size.

    Loaded from `assets/icons/brand_logo_<size>.png`.  Falls back to the
    30 px variant for any other size and lets CTkImage rescale.
    """
    from utils.resource_path import resource_path
    preferred = resource_path(f"assets/icons/brand_logo_{size}.png")
    path = preferred if preferred.exists() else resource_path("assets/icons/brand_logo_30.png")
    img = Image.open(str(path)).convert("RGBA")
    return ctk.CTkImage(light_image=img, dark_image=img, size=(size, size))


# ── Stroke icons (loaded from monochrome PNGs, tinted at runtime) ──────────────

@lru_cache(maxsize=128)
def icon(name: str, size: int = 13, color: str | None = None) -> ctk.CTkImage:
    """Return a tinted icon at the requested pixel size.

    Master art lives at `assets/icons/<name>.png` — white-on-transparent, 48 px.
    At runtime we open the master, replace its RGB channel with the tint
    colour (keeping the original alpha so anti-aliased edges stay smooth),
    then resize to `size`.  Result is LRU-cached, so repeat lookups are
    free.  Unknown names fall back to the `plus` glyph (matches the old
    behaviour).
    """
    from utils.resource_path import resource_path

    color = color or theme.TEXT_2
    rgb   = _hex_to_rgb(color)

    path = resource_path(f"assets/icons/{name}.png")
    if not path.exists():
        path = resource_path("assets/icons/plus.png")

    master = Image.open(str(path)).convert("RGBA")
    alpha  = master.split()[-1]
    tinted = Image.merge("RGBA", (
        Image.new("L", master.size, rgb[0]),
        Image.new("L", master.size, rgb[1]),
        Image.new("L", master.size, rgb[2]),
        alpha,
    ))
    final = tinted.resize((size, size), Image.LANCZOS)
    return ctk.CTkImage(light_image=final, dark_image=final, size=(size, size))
