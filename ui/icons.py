"""
PIL-rendered icons + brand logo for the design refresh.

CustomTkinter / Tk can't draw CSS gradients, real box-shadows, or SVG paths
directly. This module renders the design bundle's icons (components.jsx) at
arbitrary pixel size with antialiasing and exposes them as CTkImage instances
so they can be dropped into CTkButton(image=...) / CTkLabel(image=...).

Icons are stroke-style at strokeWidth=1.6 in a 24×24 viewBox, matching
components.jsx exactly. Each icon takes a `color` and `size` and the result is
cached.
"""
from __future__ import annotations

from functools import lru_cache
from typing import Tuple

import customtkinter as ctk
from PIL import Image, ImageDraw

from ui import theme


# ── Helpers ────────────────────────────────────────────────────────────────────

def _supersample() -> int:
    return 4   # render at 4× then downscale for AA


def _hex_to_rgb(c: str) -> Tuple[int, int, int]:
    c = c.lstrip("#")
    return int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16)


def _new_canvas(size: int) -> Tuple[Image.Image, ImageDraw.ImageDraw, float]:
    s = _supersample()
    img = Image.new("RGBA", (size * s, size * s), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    # scale: design viewBox is 24, our size is `size` px, plus supersample
    return img, d, (size * s) / 24.0


def _finalize(img: Image.Image, size: int) -> Image.Image:
    return img.resize((size, size), Image.LANCZOS)


# ── Brand logo (gradient rounded square + keyboard glyph) ──────────────────────

@lru_cache(maxsize=4)
def brand_logo(size: int = 30) -> ctk.CTkImage:
    """Replica of design's `.brand .logo`:
        background: linear-gradient(160deg, #b1e4f7 → #8c6ad6);
        border-radius: 8;
        keyboard SVG inside, white stroke, ~16px.
    """
    s = _supersample()
    px = size * s
    img = Image.new("RGBA", (px, px), (0, 0, 0, 0))

    # --- gradient fill on a rounded-rect mask -------------------------------
    grad = Image.new("RGB", (px, px), (0, 0, 0))
    g_draw = ImageDraw.Draw(grad)
    # 160° from top-left to bottom-right, approximate end colors:
    # oklch(0.85 0.12 232) ≈ light cyan #b1e4f7
    # oklch(0.62 0.16 280) ≈ violet      #8c6ad6
    a = _hex_to_rgb("#b1e4f7")
    b = _hex_to_rgb("#8c6ad6")
    # 160° ≈ mostly diagonal; do simple TL→BR linear blend along (0.34, 0.94)
    import math
    ang = math.radians(160 - 90)   # CSS uses 0deg=up, our coords use 0=right
    dx, dy = math.cos(ang), math.sin(ang)
    # project each pixel onto the direction; min..max → 0..1
    diag = abs(dx) * px + abs(dy) * px
    for y in range(px):
        for x in range(px):
            t = ((x * dx + y * dy) - min(0, dx) * px - min(0, dy) * px) / diag
            t = max(0.0, min(1.0, t))
            r = int(a[0] + (b[0] - a[0]) * t)
            g = int(a[1] + (b[1] - a[1]) * t)
            bl = int(a[2] + (b[2] - a[2]) * t)
            grad.putpixel((x, y), (r, g, bl))

    mask = Image.new("L", (px, px), 0)
    m_draw = ImageDraw.Draw(mask)
    radius = int(8 * s)
    m_draw.rounded_rectangle((0, 0, px - 1, px - 1), radius=radius, fill=255)
    img.paste(grad, (0, 0), mask)

    # subtle 1px inner highlight (design's inset shadow rgba(255,255,255,.08))
    hl = Image.new("RGBA", (px, px), (0, 0, 0, 0))
    h_draw = ImageDraw.Draw(hl)
    h_draw.rounded_rectangle((0, 0, px - 1, px - 1),
                             radius=radius, outline=(255, 255, 255, 22),
                             width=max(1, s))
    img.alpha_composite(hl)

    # keyboard glyph on top, ~16/24 of the box, white stroke ~1.6 design units
    d = ImageDraw.Draw(img)
    glyph_scale = (16 * s) / 24.0
    pad = (px - 16 * s) / 2
    sw = max(1, int(round(1.6 * glyph_scale)))
    white = (255, 255, 255, 255)

    def P(x, y): return (pad + x * glyph_scale, pad + y * glyph_scale)

    # rect 2,6 → 20×12, rx=2
    rx0, ry0 = P(2, 6); rx1, ry1 = P(22, 18)
    d.rounded_rectangle((rx0, ry0, rx1, ry1), radius=int(2 * glyph_scale),
                        outline=white, width=sw)
    # 4 dots: M6 10, M10 10, M14 10, M18 10
    dot_r = max(1, int(round(0.7 * glyph_scale)))
    for x in (6, 10, 14, 18):
        cx, cy = P(x, 10)
        d.ellipse((cx - dot_r, cy - dot_r, cx + dot_r, cy + dot_r), fill=white)
    # spacebar: M7 14 → h10
    sx0, sy0 = P(7, 14); sx1, sy1 = P(17, 14)
    d.line((sx0, sy0, sx1, sy1), fill=white, width=sw)

    final = _finalize(img, size)
    return ctk.CTkImage(light_image=final, dark_image=final, size=(size, size))


# ── SVG-stroke icons (translated from components.jsx paths) ────────────────────

def _stroke_icon(size: int, color: str, draw_fn) -> ctk.CTkImage:
    img, d, sc = _new_canvas(size)

    rgb = _hex_to_rgb(color)
    stroke = (*rgb, 255)
    sw = max(1, int(round(1.6 * sc)))

    def P(x, y): return (x * sc, y * sc)
    draw_fn(d, P, stroke, sw, sc)

    final = _finalize(img, size)
    return ctk.CTkImage(light_image=final, dark_image=final, size=(size, size))


@lru_cache(maxsize=64)
def icon(name: str, size: int = 13, color: str | None = None) -> ctk.CTkImage:
    color = color or theme.TEXT_2

    def kbd(d, P, sk, sw, sc):
        # rect 2,6 20x12 rx2
        d.rounded_rectangle((P(2, 6), P(22, 18)), radius=int(2 * sc),
                            outline=sk, width=sw)
        for x in (6, 10, 14, 18):
            cx, cy = P(x, 10); r = max(1, int(round(0.6 * sc)))
            d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=sk)
        d.line((P(7, 14), P(17, 14)), fill=sk, width=sw)

    def bolt(d, P, sk, sw, sc):
        # path d="M13 2 L4 14 L11 14 L10 22 L19 10 L12 10 L13 2 z"
        pts = [(13, 2), (4, 14), (11, 14), (10, 22), (19, 10), (12, 10)]
        d.polygon([P(*p) for p in pts], outline=sk, width=sw)

    def calendar(d, P, sk, sw, sc):
        d.rounded_rectangle((P(3, 5), P(21, 21)), radius=int(2 * sc),
                            outline=sk, width=sw)
        d.line((P(8, 3), P(8, 7)), fill=sk, width=sw)
        d.line((P(16, 3), P(16, 7)), fill=sk, width=sw)
        d.line((P(3, 10), P(21, 10)), fill=sk, width=sw)

    def clipboard(d, P, sk, sw, sc):
        d.rounded_rectangle((P(6, 4), P(18, 22)), radius=int(2 * sc),
                            outline=sk, width=sw)
        # the small clip
        d.rounded_rectangle((P(9, 4), P(15, 7)), radius=max(1, int(0.5 * sc)),
                            outline=sk, width=sw)

    def quote(d, P, sk, sw, sc):
        # two opening-quote curls, simplified to U-shapes
        # left:  M3 14 V8 H9 V14 C9 17 7 19 4 19
        d.line((P(3, 14), P(3, 8)), fill=sk, width=sw)
        d.line((P(3, 8), P(9, 8)), fill=sk, width=sw)
        d.line((P(9, 8), P(9, 14)), fill=sk, width=sw)
        d.arc((P(2, 13), P(9, 19)), 0, 90, fill=sk, width=sw)
        # right
        d.line((P(13, 14), P(13, 8)), fill=sk, width=sw)
        d.line((P(13, 8), P(19, 8)), fill=sk, width=sw)
        d.line((P(19, 8), P(19, 14)), fill=sk, width=sw)
        d.arc((P(12, 13), P(19, 19)), 0, 90, fill=sk, width=sw)

    def timer(d, P, sk, sw, sc):
        # circle 12,13 r=8
        d.ellipse((P(4, 5), P(20, 21)), outline=sk, width=sw)
        # hands
        d.line((P(12, 9), P(12, 13)), fill=sk, width=sw)
        d.line((P(12, 13), P(14, 15)), fill=sk, width=sw)
        # crown
        d.line((P(9, 2), P(15, 2)), fill=sk, width=sw)

    def lst(d, P, sk, sw, sc):
        for y in (6, 12, 18):
            d.line((P(8, y), P(21, y)), fill=sk, width=sw)
            cx, cy = P(3.5, y); r = max(1, int(round(0.9 * sc)))
            d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=sk)

    def settings(d, P, sk, sw, sc):
        d.ellipse((P(9, 9), P(15, 15)), outline=sk, width=sw)
        # 8 little spokes
        import math
        cx, cy = P(12, 12)
        for k in range(8):
            a = k * math.pi / 4
            r0 = 7.5 * sc
            r1 = 10.5 * sc
            x0 = cx + r0 * math.cos(a); y0 = cy + r0 * math.sin(a)
            x1 = cx + r1 * math.cos(a); y1 = cy + r1 * math.sin(a)
            d.line((x0, y0, x1, y1), fill=sk, width=sw)

    def plus(d, P, sk, sw, sc):
        d.line((P(12, 5), P(12, 19)), fill=sk, width=sw)
        d.line((P(5, 12), P(19, 12)), fill=sk, width=sw)

    def search(d, P, sk, sw, sc):
        d.ellipse((P(4, 4), P(18, 18)), outline=sk, width=sw)
        d.line((P(16.7, 16.7), P(21, 21)), fill=sk, width=sw)

    def chart(d, P, sk, sw, sc):
        d.line((P(3, 3), P(3, 21)), fill=sk, width=sw)
        d.line((P(3, 21), P(21, 21)), fill=sk, width=sw)
        # zig
        d.line((P(7, 14), P(11, 10)), fill=sk, width=sw)
        d.line((P(11, 10), P(15, 14)), fill=sk, width=sw)
        d.line((P(15, 14), P(20, 8)), fill=sk, width=sw)

    def stickynote(d, P, sk, sw, sc):
        d.rounded_rectangle((P(3, 3), P(21, 21)), radius=int(2 * sc),
                            outline=sk, width=sw)
        d.line((P(16, 21), P(16, 16)), fill=sk, width=sw)
        d.line((P(16, 16), P(21, 16)), fill=sk, width=sw)

    def chevU(d, P, sk, sw, sc):
        d.line((P(6, 15), P(12, 9)), fill=sk, width=sw)
        d.line((P(12, 9), P(18, 15)), fill=sk, width=sw)

    def chevD(d, P, sk, sw, sc):
        d.line((P(6, 9), P(12, 15)), fill=sk, width=sw)
        d.line((P(12, 15), P(18, 9)), fill=sk, width=sw)

    def chevL(d, P, sk, sw, sc):
        d.line((P(15, 18), P(9, 12)), fill=sk, width=sw)
        d.line((P(9, 12), P(15, 6)), fill=sk, width=sw)

    def chevR(d, P, sk, sw, sc):
        d.line((P(9, 18), P(15, 12)), fill=sk, width=sw)
        d.line((P(15, 12), P(9, 6)), fill=sk, width=sw)

    def download(d, P, sk, sw, sc):
        d.line((P(3, 15), P(3, 19)), fill=sk, width=sw)
        d.line((P(3, 19), P(21, 19)), fill=sk, width=sw)
        d.line((P(21, 19), P(21, 15)), fill=sk, width=sw)
        d.line((P(7, 10), P(12, 15)), fill=sk, width=sw)
        d.line((P(12, 15), P(17, 10)), fill=sk, width=sw)
        d.line((P(12, 3), P(12, 15)), fill=sk, width=sw)

    def upload(d, P, sk, sw, sc):
        d.line((P(3, 15), P(3, 19)), fill=sk, width=sw)
        d.line((P(3, 19), P(21, 19)), fill=sk, width=sw)
        d.line((P(21, 19), P(21, 15)), fill=sk, width=sw)
        d.line((P(7, 8), P(12, 3)), fill=sk, width=sw)
        d.line((P(12, 3), P(17, 8)), fill=sk, width=sw)
        d.line((P(12, 3), P(12, 15)), fill=sk, width=sw)

    def folder(d, P, sk, sw, sc):
        # M3 7 a2 2 0 012-2 h4 l2 2 h8 a2 2 0 012 2 v9 a2 2 0 01-2 2 H5 a2 2 0 01-2-2z
        # simplified to a polygon
        pts = [(3, 7), (5, 5), (9, 5), (11, 7), (19, 7), (21, 9),
               (21, 18), (19, 20), (5, 20), (3, 18)]
        d.line([P(*p) for p in pts] + [P(*pts[0])], fill=sk, width=sw, joint="curve")

    def edit(d, P, sk, sw, sc):
        # underline at y=20
        d.line((P(12, 20), P(21, 20)), fill=sk, width=sw)
        # pencil body — diamond shape
        pts = [(16.5, 3.5), (19.5, 6.5), (7, 19), (3, 20), (4, 16)]
        d.line([P(*p) for p in pts] + [P(*pts[0])],
               fill=sk, width=sw, joint="curve")

    def trash(d, P, sk, sw, sc):
        # top rim
        d.line((P(3, 6), P(21, 6)), fill=sk, width=sw)
        # lid handle (small bump)
        d.line((P(8, 6), P(8, 4)), fill=sk, width=sw)
        d.line((P(8, 4), P(16, 4)), fill=sk, width=sw)
        d.line((P(16, 4), P(16, 6)), fill=sk, width=sw)
        # bottom box
        pts = [(5, 6), (6, 21), (18, 21), (19, 6)]
        d.line([P(*p) for p in pts], fill=sk, width=sw, joint="curve")
        # vertical stripes inside
        d.line((P(10, 11), P(10, 17)), fill=sk, width=sw)
        d.line((P(14, 11), P(14, 17)), fill=sk, width=sw)

    def dupe(d, P, sk, sw, sc):
        # front sheet (lower-right)
        d.rounded_rectangle((P(9, 9), P(20, 20)), radius=int(2 * sc),
                            outline=sk, width=sw)
        # back sheet (L-shape behind)
        pts = [(9, 5), (4, 5), (4, 16), (8, 16)]   # L outline
        d.line([P(*p) for p in pts], fill=sk, width=sw, joint="curve")
        d.line((P(15, 5), P(15, 8)), fill=sk, width=sw)

    paths = {
        "keyboard":   kbd,
        "bolt":       bolt,
        "calendar":   calendar,
        "clipboard":  clipboard,
        "quote":      quote,
        "timer":      timer,
        "list":       lst,
        "settings":   settings,
        "plus":       plus,
        "search":     search,
        "chart":      chart,
        "stickynote": stickynote,
        "chevU":      chevU,
        "chevD":      chevD,
        "chevL":      chevL,
        "chevR":      chevR,
        "download":   download,
        "upload":     upload,
        "folder":     folder,
        "edit":       edit,
        "trash":      trash,
        "dupe":       dupe,
    }
    fn = paths.get(name, plus)
    return _stroke_icon(size, color, fn)
