"""
Design tokens for HotkeyTool's UI Refresh.

Translated from the design bundle's styles.css. The original used OKLCH colors
for the accent / success / danger ramps; Tk doesn't speak OKLCH so each value
has been pre-converted to its closest sRGB hex equivalent.

Everything visual in the app should pull from this module — never hardcode a
color or font in a tab file.
"""
from __future__ import annotations

import customtkinter as ctk

# ── Backgrounds ────────────────────────────────────────────────────────────────
BG_BASE       = "#0a0c11"
BG_TITLEBAR   = "#0e1117"
BG_SURFACE    = "#11141b"
BG_ELEVATED   = "#171b24"
BG_ROW        = "#181c25"
BG_ROW_ALT    = "#161922"
BG_HOVER      = "#1f2430"
BG_INPUT      = "#0e1117"

# ── Borders ────────────────────────────────────────────────────────────────────
BORDER        = "#232733"
BORDER_SOFT   = "#1c2029"
BORDER_STRONG = "#2c313f"

# ── Text ───────────────────────────────────────────────────────────────────────
TEXT_1        = "#e6e8ef"
TEXT_2        = "#a1a7b8"
TEXT_3        = "#6b7185"
TEXT_4        = "#464c5c"

# ── Accent (cool blue, oklch(0.80 0.10 232)) ───────────────────────────────────
ACCENT        = "#7fc6e6"
ACCENT_MID    = "#5fb1d8"
ACCENT_DEEP   = "#3a86a8"
ACCENT_BG     = "#162834"   # accent at ~10% on bg-base
ACCENT_BG_2   = "#1d3a4b"   # accent at ~18%
ACCENT_BORDER = "#27485c"   # accent at ~25%
ACCENT_TEXT   = "#0a1218"   # for text on accent fill (e.g. today circle)

# ── Status ramps ───────────────────────────────────────────────────────────────
SUCCESS        = "#5fd1a0"   # oklch(0.78 0.14 152)
SUCCESS_DEEP   = "#2a8a64"
SUCCESS_BG     = "#142421"
SUCCESS_BORDER = "#1f3c33"

DANGER         = "#e88a78"   # oklch(0.72 0.16 22)
DANGER_DEEP    = "#b04030"
DANGER_BG      = "#2a1a18"
DANGER_BORDER  = "#3f2520"

WARNING        = "#e6b86a"   # oklch(0.82 0.13 75)
WARNING_BG     = "#2a2218"

PURPLE         = "#b89cd6"   # oklch(0.78 0.12 295)
PINK           = "#d6a0bb"   # oklch(0.78 0.13 350)

# ── Priority ramp (planner) ────────────────────────────────────────────────────
PRI_LOW        = "#7fc0c6"
PRI_MEDIUM     = "#e6b86a"
PRI_HIGH       = "#e88a78"

# ── Category dots (planner) ────────────────────────────────────────────────────
CAT_PALETTE = [
    "#7fc6e6",  # accent blue
    "#b89cd6",  # purple
    "#e6b86a",  # warm yellow
    "#5fd1a0",  # green
    "#d6a0bb",  # pink
    "#7fc0c6",  # teal
    "#e8a378",  # orange
    "#9cc6e6",  # soft blue
    "#c6c6c6",  # neutral
]

# ── Radii ──────────────────────────────────────────────────────────────────────
RADIUS_SM = 6
RADIUS    = 8
RADIUS_LG = 12

# ── Fonts ──────────────────────────────────────────────────────────────────────
# Resolved at first call to font()/mono(); set by utils.fonts.load_app_fonts().
_FONT_FAMILY      = "Segoe UI"
_FONT_FAMILY_MONO = "Consolas"


def set_font_families(sans: str, mono_: str) -> None:
    """Called by utils.fonts.load_app_fonts() once Geist is loaded successfully.
    Falls through silently if Geist isn't available."""
    global _FONT_FAMILY, _FONT_FAMILY_MONO
    _FONT_FAMILY = sans
    _FONT_FAMILY_MONO = mono_


def font(size: int = 13, weight: str = "normal") -> ctk.CTkFont:
    """Sans font (Geist if loaded, Segoe UI fallback)."""
    return ctk.CTkFont(family=_FONT_FAMILY, size=size, weight=weight)


def mono(size: int = 12, weight: str = "normal") -> ctk.CTkFont:
    """Monospace font (Geist Mono if loaded, Consolas fallback).

    Used for hotkey chips, timer digits, clock, dates, count badges.
    """
    return ctk.CTkFont(family=_FONT_FAMILY_MONO, size=size, weight=weight)


def font_family() -> str:
    return _FONT_FAMILY


def mono_family() -> str:
    return _FONT_FAMILY_MONO


# ── Easing + tween helper ──────────────────────────────────────────────────────

def ease_out_cubic(t: float) -> float:
    return 1 - (1 - t) ** 3


def ease_spring(t: float) -> float:
    """Slight overshoot, bouncy settle — matches design's --spring."""
    # cubic-bezier(.34,1.56,.64,1) approximation
    if t >= 1.0:
        return 1.0
    return 1 + 2.70158 * (t - 1) ** 3 + 1.70158 * (t - 1) ** 2


def tween(widget, setter, frm: float, to: float, ms: int = 280,
          ease=ease_out_cubic, fps: int = 60) -> None:
    """Drive `setter(value)` from `frm` → `to` over `ms` milliseconds.

    Cancellable: if the widget is destroyed mid-tween the after() chain dies
    quietly. No-op when the widget is not displayable.
    """
    try:
        if not widget.winfo_exists():
            return
    except Exception:
        return

    steps = max(2, int(ms * fps / 1000))
    delta = to - frm

    def step(i: int) -> None:
        try:
            if not widget.winfo_exists():
                return
        except Exception:
            return
        t = i / steps
        v = frm + delta * ease(t)
        try:
            setter(v)
        except Exception:
            return
        if i < steps:
            widget.after(int(ms / steps), step, i + 1)
        else:
            try:
                setter(to)
            except Exception:
                pass

    widget.after(0, step, 1)
