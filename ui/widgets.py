"""
Shared widget primitives — replaces dozens of inline lookalikes scattered
across the tab files. Every widget here pulls colors / fonts from ui.theme.

Animation strategy: Tk has no first-class transitions, so anything that "moves"
(switch thumb, tab indicator, pulse, count tween, toast slide) is driven by
tiny after()-loops via theme.tween() or a dedicated _pulse() loop.
"""
from __future__ import annotations

import tkinter as tk
from typing import Callable, Iterable, List, Optional, Tuple

import customtkinter as ctk

from ui import theme


# ════════════════════════════════════════════════════════════════════════════════
# Buttons — design's .btn variants
# ════════════════════════════════════════════════════════════════════════════════

def _btn_auto_width(text: str, *, font_size: int, icon: bool, small: bool,
                    weight: str = "normal") -> int:
    """Compute a button width that fits the label + design's horizontal padding.

    Design: .btn padding 0 14px (28 total), .btn-sm padding 0 10px (20 total).
    CTkButton has no auto-sizing — passing width=0 clips the label. We measure
    the actual rendered text via tkinter's font metrics (Tk root required, which
    callers already have when constructing widgets).
    """
    horiz_pad = 20 if small else 28
    if not text:
        return 28 if small else 32
    icon_w = (font_size + 10) if icon else 0  # icon px + 8px gap
    try:
        from tkinter.font import Font
        f = Font(family=theme.font_family(), size=font_size, weight=weight)
        text_w = f.measure(text)
    except Exception:
        text_w = int(len(text) * font_size * 0.7)
    return text_w + icon_w + horiz_pad + 4   # +4 safety against rounding


def _attach_press_anim(btn: ctk.CTkButton) -> None:
    """Subtle press feedback — design's `:active { transform: scale(.97); }`.
    Tk can't scale, so we briefly dim the fg_color instead."""
    try:
        rest = btn.cget("fg_color")
    except Exception:
        return

    def _press(_e=None):
        try: btn.configure(fg_color=btn.cget("hover_color"))
        except Exception: pass

    def _release(_e=None):
        try: btn.configure(fg_color=rest)
        except Exception: pass

    btn.bind("<ButtonPress-1>", _press, add="+")
    btn.bind("<ButtonRelease-1>", _release, add="+")


def PrimaryButton(parent, text: str = "", command=None, *, width: int = 0,
                  height: int = 32, icon: str | None = None,
                  small: bool = False, **kw) -> ctk.CTkButton:
    if small:
        height = 26
    font_size = 11 if small else 12
    if not width:
        width = _btn_auto_width(text, font_size=font_size,
                                icon=bool(icon), small=small,
                                weight="bold")
    btn = ctk.CTkButton(
        parent,
        text=(f"{icon}  {text}" if icon else text),
        command=command,
        width=width,
        height=height,
        corner_radius=theme.RADIUS_SM if small else theme.RADIUS,
        fg_color=theme.ACCENT_MID,
        hover_color=theme.ACCENT,
        text_color=theme.ACCENT_TEXT,
        font=theme.font(font_size, "bold"),
        border_width=0,
        **kw,
    )
    _attach_press_anim(btn)
    return btn


def GhostButton(parent, text: str = "", command=None, *, width: int = 0,
                height: int = 32, icon: str | None = None,
                small: bool = False, **kw) -> ctk.CTkButton:
    if small:
        height = 26
    font_size = 11 if small else 12
    if not width:
        width = _btn_auto_width(text, font_size=font_size,
                                icon=bool(icon), small=small,
                                weight="normal")
    btn = ctk.CTkButton(
        parent,
        text=(f"{icon}  {text}" if icon else text),
        command=command,
        width=width,
        height=height,
        corner_radius=theme.RADIUS_SM if small else theme.RADIUS,
        fg_color=theme.BG_ELEVATED,
        hover_color=theme.BG_HOVER,
        text_color=theme.TEXT_1,
        border_color=theme.BORDER,
        border_width=1,
        font=theme.font(font_size, "normal"),
        **kw,
    )
    _attach_press_anim(btn)
    return btn


def DangerButton(parent, text: str = "", command=None, *, width: int = 0,
                 height: int = 32, icon: str | None = None,
                 small: bool = False, **kw) -> ctk.CTkButton:
    if small:
        height = 26
    font_size = 11 if small else 12
    if not width:
        width = _btn_auto_width(text, font_size=font_size,
                                icon=bool(icon), small=small,
                                weight="normal")
    btn = ctk.CTkButton(
        parent,
        text=(f"{icon}  {text}" if icon else text),
        command=command,
        width=width,
        height=height,
        corner_radius=theme.RADIUS_SM if small else theme.RADIUS,
        fg_color=theme.DANGER_BG,
        hover_color=theme.DANGER_BORDER,
        text_color=theme.DANGER,
        border_color=theme.DANGER_BORDER,
        border_width=1,
        font=theme.font(font_size, "normal"),
        **kw,
    )
    _attach_press_anim(btn)
    return btn


def SuccessButton(parent, text: str = "", command=None, *, width: int = 0,
                  height: int = 32, icon: str | None = None,
                  small: bool = False, **kw) -> ctk.CTkButton:
    if small:
        height = 26
    font_size = 11 if small else 12
    if not width:
        width = _btn_auto_width(text, font_size=font_size,
                                icon=bool(icon), small=small,
                                weight="normal")
    btn = ctk.CTkButton(
        parent,
        text=(f"{icon}  {text}" if icon else text),
        command=command,
        width=width,
        height=height,
        corner_radius=theme.RADIUS_SM if small else theme.RADIUS,
        fg_color=theme.SUCCESS_BG,
        hover_color=theme.SUCCESS_BORDER,
        text_color=theme.SUCCESS,
        border_color=theme.SUCCESS_BORDER,
        border_width=1,
        font=theme.font(font_size, "normal"),
        **kw,
    )
    _attach_press_anim(btn)
    return btn


def HeaderButton(parent, text: str = "", command=None, *, image=None,
                 height: int = 32, **kw) -> ctk.CTkButton:
    """Design's `.icon-btn`: transparent bg, 1px border, gap 6 between icon
    and text. Used in the app header for Stats / Notes.
    """
    font_size = 12
    width = _btn_auto_width(text, font_size=font_size,
                            icon=image is not None, small=False)
    btn = ctk.CTkButton(
        parent,
        text=text,
        image=image,
        compound="left",
        command=command,
        width=width,
        height=height,
        corner_radius=theme.RADIUS,
        fg_color="transparent",
        hover_color=theme.BG_HOVER,
        text_color=theme.TEXT_2,
        border_color=theme.BORDER,
        border_width=1,
        font=theme.font(font_size, "normal"),
        **kw,
    )

    def _hover_in(_e=None):
        try: btn.configure(text_color=theme.TEXT_1, border_color=theme.BORDER_STRONG)
        except Exception: pass

    def _hover_out(_e=None):
        try: btn.configure(text_color=theme.TEXT_2, border_color=theme.BORDER)
        except Exception: pass

    btn.bind("<Enter>", _hover_in, add="+")
    btn.bind("<Leave>", _hover_out, add="+")
    _attach_press_anim(btn)
    return btn


def IconButton(parent, icon: str = "", command=None, *, kind: str = "ghost",
               size: int = 28, image=None, **kw) -> ctk.CTkButton:
    """Square icon-only button. Pass `icon` for a glyph string, or `image`
    for a PIL/CTkImage (preferred — Geist doesn't carry many symbol glyphs)."""
    text = "" if image is not None else icon
    extra = {"image": image} if image is not None else {}
    extra.update(kw)
    factory = {
        "ghost":   lambda: GhostButton  (parent, text=text, command=command, width=size, height=size, **extra),
        "danger":  lambda: DangerButton (parent, text=text, command=command, width=size, height=size, **extra),
        "success": lambda: SuccessButton(parent, text=text, command=command, width=size, height=size, **extra),
        "primary": lambda: PrimaryButton(parent, text=text, command=command, width=size, height=size, **extra),
    }[kind]
    btn = factory()
    btn.configure(corner_radius=theme.RADIUS_SM)
    return btn


# ════════════════════════════════════════════════════════════════════════════════
# Hotkey chip — design .hk / .hk-key
# ════════════════════════════════════════════════════════════════════════════════

class HotkeyChip(ctk.CTkFrame):
    """Renders a hotkey like `Ctrl+Alt+G` with each key in its own bordered
    chip on accent-tinted background.

    Half the previous height — design targets a single-line ~22px-tall pill.
    Width grows naturally with the number of keys; `pack_propagate` stays True
    so the parent frame fits all keys without clipping.
    """
    def __init__(self, parent, keys: Optional[str] = None, *, dim: bool = False, **kw):
        bg = theme.BG_ELEVATED if dim else theme.ACCENT_BG
        border = theme.BORDER_SOFT if dim else theme.ACCENT_BORDER
        text = theme.TEXT_3 if dim else theme.ACCENT
        super().__init__(parent, fg_color=bg, corner_radius=5,
                         border_color=border, border_width=1, **kw)
        self._dim = dim
        if not keys:
            ctk.CTkLabel(self, text="—", font=theme.mono(10),
                         text_color=text, height=14,
                         ).pack(padx=8, pady=2)
            return

        parts = [k.strip().upper() for k in keys.split("+") if k.strip()]
        for i, k in enumerate(parts):
            is_last = i == len(parts) - 1
            key_bg = theme.BG_ROW if dim else theme.ACCENT_BG_2
            key_chip = ctk.CTkLabel(
                self, text=k, font=theme.mono(9, "bold"),
                text_color=text, fg_color=key_bg,
                corner_radius=3, padx=3, height=14,
            )
            key_chip.pack(side="left",
                          padx=(4 if i == 0 else 2, 5 if is_last else 0),
                          pady=2)
            if not is_last:
                ctk.CTkLabel(
                    self, text="+", font=theme.font(9),
                    text_color=text, height=14,
                ).pack(side="left", padx=1)


# ════════════════════════════════════════════════════════════════════════════════
# Switch — small pill with sliding thumb
# ════════════════════════════════════════════════════════════════════════════════

class Switch(tk.Canvas):
    """Compact switch (32×18) with a sliding thumb.

    Track and thumb are both PIL-rendered RGBA images at 4× supersample then
    downscaled, so the pill ends are smooth and the thumb is anti-aliased.
    Track has TRANSPARENT corners — the Canvas bg shows through, which lets
    us follow the row's current bg color without re-rendering on hover (just
    `canvas.configure(bg=new_bg)` via _refresh_bg).
    """
    _W       = 32
    _H       = 18
    _PAD     = 3
    _THUMB_D = 12   # smaller + rounder (was 14)

    _track_cache: dict = {}
    _thumb_cache: dict = {}

    def __init__(self, parent, on: bool = False, command: Callable[[bool], None] | None = None):
        super().__init__(parent, width=self._W, height=self._H,
                         bg=self._parent_bg(parent), highlightthickness=0,
                         bd=0, cursor="hand2")
        self._on = on
        self._cmd = command
        self._thumb_x = self._target_x()
        self._track_id = None
        self._thumb_id = None
        self._track_ref = None
        self._thumb_ref = None
        self._draw()
        self.bind("<Button-1>", self._toggle)

    def _parent_bg(self, parent) -> str:
        try:
            color = parent.cget("fg_color")
            if isinstance(color, (list, tuple)):
                color = color[1]
            if isinstance(color, str) and color.startswith("#"):
                return color
        except Exception:
            pass
        return theme.BG_ROW

    def _target_x(self) -> float:
        return self._W - self._THUMB_D - self._PAD if self._on else self._PAD

    @staticmethod
    def _hex(c: str) -> tuple:
        c = c.lstrip("#")
        return int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16)

    @classmethod
    def _track_image(cls, on: bool):
        from PIL import Image, ImageDraw, ImageTk
        cached = cls._track_cache.get(on)
        if cached is not None:
            return cached
        s = 4
        W, H = cls._W * s, cls._H * s
        track_bg     = theme.SUCCESS_BG     if on else theme.BG_ELEVATED
        track_border = theme.SUCCESS_BORDER if on else theme.BORDER
        img = Image.new("RGBA", (W, H), (0, 0, 0, 0))   # transparent corners
        d = ImageDraw.Draw(img)
        d.rounded_rectangle(
            (0, 0, W - 1, H - 1), radius=H // 2,
            fill=cls._hex(track_bg) + (255,),
            outline=cls._hex(track_border) + (255,),
            width=max(1, s),
        )
        img = img.resize((cls._W, cls._H), Image.LANCZOS)
        photo = ImageTk.PhotoImage(img)
        cls._track_cache[on] = photo
        return photo

    @classmethod
    def _thumb_image(cls, color: str):
        from PIL import Image, ImageDraw, ImageTk
        cached = cls._thumb_cache.get(color)
        if cached is not None:
            return cached
        s = 4
        d_px = cls._THUMB_D
        W = H = d_px * s
        img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        ImageDraw.Draw(img).ellipse(
            (0, 0, W - 1, H - 1), fill=cls._hex(color) + (255,),
        )
        img = img.resize((d_px, d_px), Image.LANCZOS)
        photo = ImageTk.PhotoImage(img)
        cls._thumb_cache[color] = photo
        return photo

    def _draw(self) -> None:
        # Refresh canvas bg to track parent (in case the row has hovered).
        self.configure(bg=self._parent_bg(self.master))

        track = Switch._track_image(self._on)
        thumb_color = theme.SUCCESS if self._on else theme.TEXT_3
        thumb = Switch._thumb_image(thumb_color)
        self._track_ref = track
        self._thumb_ref = thumb

        if self._track_id is None:
            self._track_id = self.create_image(0, 0, anchor="nw", image=track)
            self._thumb_id = self.create_image(
                int(self._thumb_x), self._PAD, anchor="nw", image=thumb)
        else:
            self.itemconfigure(self._track_id, image=track)
            self.itemconfigure(self._thumb_id, image=thumb)
            self.coords(self._thumb_id, int(self._thumb_x), self._PAD)

    def _refresh_bg(self) -> None:
        """Hook for Row hover handlers — keep canvas bg in sync with row's bg."""
        try:
            self.configure(bg=self._parent_bg(self.master))
        except Exception:
            pass

    def _toggle(self, _evt=None) -> None:
        self.set(not self._on, animate=True)
        if self._cmd:
            self._cmd(self._on)

    def set(self, on: bool, *, animate: bool = False) -> None:
        if on == self._on:
            return
        self._on = on
        if not animate:
            self._thumb_x = self._target_x()
            self._draw()
            return

        target = self._target_x()
        start = self._thumb_x
        def setter(v):
            self._thumb_x = v
            self._draw()
        theme.tween(self, setter, start, target, ms=220, ease=theme.ease_spring)

    def is_on(self) -> bool:
        return self._on


# ════════════════════════════════════════════════════════════════════════════════
# Row — base row container with hover + revealed actions
# ════════════════════════════════════════════════════════════════════════════════

class Row(ctk.CTkFrame):
    """Row container with subtle hover bg + actions area that reveals on hover.

    Hover detection: Tk's <Enter>/<Leave> only fire on the bare row surface —
    children consume the event for their own area. We walk descendants once
    the row is built and bind the same handlers to each one, so hovering over
    *any* part of the row counts. Each handler still uses pointer-position
    checks to ignore intra-row pointer moves between children.
    """
    def __init__(self, parent, *, dim: bool = False, **kw):
        super().__init__(
            parent,
            fg_color=theme.BG_ROW,
            corner_radius=10,
            border_color=theme.BORDER_SOFT,
            border_width=1,
            **kw,
        )
        self._dim = dim
        self._hovered = False
        self._reveal_cb = None
        self._hover_widgets: set = set()
        self._watchdog_id: str | None = None
        self.bind("<Enter>", self._on_enter, add="+")
        self.bind("<Leave>", self._on_leave, add="+")
        # Defer descendant binding until after the subclass finishes _build().
        self.after(60, self._attach_hover_to_descendants)

    def _attach_hover_to_descendants(self, root: tk.Widget | None = None) -> None:
        root = root or self
        try:
            for c in root.winfo_children():
                if c not in self._hover_widgets:
                    self._hover_widgets.add(c)
                    try:
                        c.bind("<Enter>", self._on_enter, add="+")
                        c.bind("<Leave>", self._on_leave, add="+")
                    except Exception:
                        pass
                self._attach_hover_to_descendants(c)
        except Exception:
            pass

    def set_actions_widget(self, widget: tk.Widget, packed_kwargs: dict | None = None) -> None:
        """Register the widget that should appear/disappear on hover."""
        self._actions = widget
        self._actions_kwargs = packed_kwargs or {"side": "right"}
        widget.pack_forget()
        self._attach_hover_to_descendants(widget)

    def _pointer_in_row(self) -> bool:
        try:
            x, y = self.winfo_pointerxy()
            x0, y0 = self.winfo_rootx(), self.winfo_rooty()
            x1, y1 = x0 + self.winfo_width(), y0 + self.winfo_height()
            return x0 <= x <= x1 and y0 <= y <= y1
        except Exception:
            return False

    def _notify_bg_change(self) -> None:
        """Walk descendants and call _refresh_bg if present (Switch needs this
        to keep its canvas bg in sync with the row's hover state)."""
        def walk(w):
            for c in w.winfo_children():
                if hasattr(c, "_refresh_bg"):
                    try: c._refresh_bg()
                    except Exception: pass
                walk(c)
        walk(self)

    def _on_enter(self, _evt=None) -> None:
        if self._hovered:
            return
        self._hovered = True
        self.configure(fg_color=theme.BG_HOVER, border_color=theme.BORDER)
        if hasattr(self, "_actions"):
            try:
                self._actions.pack(**self._actions_kwargs)
            except Exception:
                pass
        self._notify_bg_change()
        # Watchdog: Tk occasionally drops <Leave> events (fast pointer move,
        # another window appearing over the pointer, modal dialog stealing
        # focus, …) which would leave the row stuck in the hovered state.
        # Poll every 250 ms while hovered and force-clear if the pointer is
        # not actually inside the row anymore.
        self._start_watchdog()

    def _on_leave(self, _evt=None) -> None:
        if not self._hovered:
            return
        # Defer the actual check by one frame so the pointer coordinates
        # settle after moving between child widgets — prevents false deselects.
        self.after(15, self._deferred_leave_check)

    def _deferred_leave_check(self) -> None:
        if not self._hovered:
            return
        if self._pointer_in_row():
            return
        self._do_leave()

    def _start_watchdog(self) -> None:
        if self._watchdog_id is not None:
            return
        try:
            self._watchdog_id = self.after(250, self._watchdog_tick)
        except Exception:
            self._watchdog_id = None

    def _watchdog_tick(self) -> None:
        self._watchdog_id = None
        if not self._hovered:
            return
        try:
            if not self.winfo_exists():
                return
        except Exception:
            return
        if not self._pointer_in_row():
            # Pointer is gone but we never received <Leave> — force-clear.
            self._do_leave()
            return
        self._start_watchdog()

    def _do_leave(self) -> None:
        self._hovered = False
        if self._watchdog_id is not None:
            try:
                self.after_cancel(self._watchdog_id)
            except Exception:
                pass
            self._watchdog_id = None
        try:
            self.configure(fg_color=theme.BG_ROW, border_color=theme.BORDER_SOFT)
        except Exception:
            pass
        if hasattr(self, "_actions"):
            try:
                self._actions.pack_forget()
            except Exception:
                pass
        self._notify_bg_change()


# ════════════════════════════════════════════════════════════════════════════════
# Section card — rounded elevated frame (settings groups)
# ════════════════════════════════════════════════════════════════════════════════

class SectionCard(ctk.CTkFrame):
    def __init__(self, parent, **kw):
        super().__init__(
            parent,
            fg_color=theme.BG_ELEVATED,
            corner_radius=theme.RADIUS_LG,
            border_color=theme.BORDER_SOFT,
            border_width=1,
            **kw,
        )


def section_title(parent, text: str, **kw) -> ctk.CTkLabel:
    return ctk.CTkLabel(
        parent, text=text.upper(),
        font=theme.font(10, "bold"),
        text_color=theme.TEXT_3,
        anchor="w",
        **kw,
    )


# ════════════════════════════════════════════════════════════════════════════════
# Search input — bordered, icon left, focus ring
# ════════════════════════════════════════════════════════════════════════════════

class Search(ctk.CTkFrame):
    def __init__(self, parent, placeholder: str = "Search…",
                 on_change: Callable[[str], None] | None = None, *,
                 width: int = 320, height: int = 32, **kw):
        super().__init__(
            parent, fg_color=theme.BG_INPUT, corner_radius=theme.RADIUS_SM,
            border_color=theme.ACCENT_BORDER, border_width=1,
            width=width, height=height, **kw,
        )
        self.pack_propagate(False)
        self._on_change = on_change

        from ui.icons import icon as ui_icon
        ctk.CTkLabel(
            self, text="", image=ui_icon("search", 13, theme.TEXT_3),
            fg_color="transparent", width=18,
        ).pack(side="left", padx=(10, 8))

        self._entry = ctk.CTkEntry(
            self,
            placeholder_text=placeholder,
            fg_color="transparent",
            border_width=0,
            text_color=theme.TEXT_1,
            placeholder_text_color=theme.TEXT_2,
            font=theme.font(12),
        )
        self._entry.pack(side="left", fill="both", expand=True, padx=(0, 10))
        self._entry.bind("<KeyRelease>", self._fire)
        self._entry.bind("<FocusIn>",  lambda _e: self.configure(border_color=theme.ACCENT_MID))
        self._entry.bind("<FocusOut>", lambda _e: self.configure(border_color=theme.ACCENT_BORDER))

    def _fire(self, *_a) -> None:
        if self._on_change:
            self._on_change(self._entry.get())

    def get(self) -> str:
        return self._entry.get()

    def set(self, v: str) -> None:
        self._entry.delete(0, "end")
        self._entry.insert(0, v)


# ════════════════════════════════════════════════════════════════════════════════
# AnimatedCount — label whose number tweens between values
# ════════════════════════════════════════════════════════════════════════════════

class AnimatedCount(ctk.CTkLabel):
    def __init__(self, parent, value: int = 0, *,
                 fmt: Callable[[int], str] | None = None, **kw):
        self._value = value
        self._fmt = fmt or (lambda v: str(v))
        super().__init__(parent, text=self._fmt(value), **kw)

    def set(self, value: int) -> None:
        if value == self._value:
            return
        start = self._value
        end = value
        self._value = end
        def setter(v):
            try:
                self.configure(text=self._fmt(int(round(v))))
            except Exception:
                pass
        theme.tween(self, setter, start, end, ms=350, ease=theme.ease_out_cubic)


# ════════════════════════════════════════════════════════════════════════════════
# Listening pill — pulsing dot + label, top-right of header
# ════════════════════════════════════════════════════════════════════════════════

class ListenPill(ctk.CTkFrame):
    def __init__(self, parent, listening: bool, command: Callable[[], None],
                 active_count_getter: Callable[[], int] | None = None):
        super().__init__(parent, fg_color=parent.cget("fg_color"))
        self._cmd = command
        self._active_getter = active_count_getter or (lambda: 0)

        self._inner = ctk.CTkFrame(
            self, corner_radius=15, height=30,
            fg_color=theme.SUCCESS_BG,
            border_color=theme.SUCCESS_BORDER, border_width=1,
        )
        self._inner.pack()
        self._inner.pack_propagate(False)

        self._pulse_canvas = tk.Canvas(
            self._inner, width=14, height=14, bg=theme.SUCCESS_BG,
            highlightthickness=0, bd=0,
        )
        self._pulse_canvas.pack(side="left", padx=(10, 0))

        self._label = ctk.CTkLabel(
            self._inner, text="Listening", font=theme.font(11, "normal"),
            text_color=theme.SUCCESS, fg_color="transparent",
        )
        self._label.pack(side="left", padx=(8, 4))

        self._count = ctk.CTkLabel(
            self._inner, text="", font=theme.font(11),
            text_color=theme.SUCCESS, fg_color="transparent",
        )
        self._count.pack(side="left", padx=(0, 12))

        # Click handlers — bind on every child so anywhere on the pill triggers
        for w in (self._inner, self._pulse_canvas, self._label, self._count):
            w.bind("<Button-1>", lambda _e: self._cmd())
            try:
                w.configure(cursor="hand2")
            except Exception:
                pass
        self._inner.bind("<Enter>", lambda _e: self._on_hover(True))
        self._inner.bind("<Leave>", lambda _e: self._on_hover(False))

        self._listening = listening
        self._pulse_phase = 0.0
        self._pulse_running = False
        self.set_listening(listening)

    def _on_hover(self, hover: bool) -> None:
        if self._listening:
            self._inner.configure(fg_color=theme.SUCCESS_BORDER if hover else theme.SUCCESS_BG)
        else:
            self._inner.configure(fg_color=theme.DANGER_BORDER if hover else theme.DANGER_BG)

    def set_listening(self, listening: bool) -> None:
        self._listening = listening
        if listening:
            self._inner.configure(fg_color=theme.SUCCESS_BG, border_color=theme.SUCCESS_BORDER)
            self._label.configure(text="Listening", text_color=theme.SUCCESS)
            self._count.configure(text_color=theme.SUCCESS)
            self._pulse_canvas.configure(bg=theme.SUCCESS_BG)
            self._start_pulse()
        else:
            self._inner.configure(fg_color=theme.DANGER_BG, border_color=theme.DANGER_BORDER)
            self._label.configure(text="Paused", text_color=theme.DANGER)
            self._count.configure(text_color=theme.DANGER)
            self._pulse_canvas.configure(bg=theme.DANGER_BG)
            self._pulse_running = False
            self._draw_pulse(static=True)
        self.set_active_count(self._active_getter())

    def set_active_count(self, n: int) -> None:
        if n > 0:
            self._count.configure(text=f"·  {n} active")
        else:
            self._count.configure(text="")

    # ── pulse animation ──
    def _start_pulse(self) -> None:
        if self._pulse_running:
            return
        self._pulse_running = True
        self._pulse_phase = 0.0
        self._tick_pulse()

    def _tick_pulse(self) -> None:
        if not self._pulse_running or not self.winfo_exists():
            return
        self._pulse_phase = (self._pulse_phase + 0.04) % 1.0
        self._draw_pulse()
        self.after(33, self._tick_pulse)

    def _draw_pulse(self, *, static: bool = False) -> None:
        c = self._pulse_canvas
        c.delete("all")
        cx, cy = 7, 7
        color = theme.SUCCESS if self._listening else theme.DANGER
        # core dot
        c.create_oval(cx - 3, cy - 3, cx + 3, cy + 3, fill=color, outline="")
        if static:
            return
        # animated halo: grows from r=3 to r=7 then fades
        t = self._pulse_phase
        r = 3 + 4 * t
        # opacity hint via stipple (Tk canvas doesn't do alpha directly)
        if t < 0.7:
            c.create_oval(cx - r, cy - r, cx + r, cy + r,
                          outline=color, width=1)


# ════════════════════════════════════════════════════════════════════════════════
# Toast — bottom-center floating label
# ════════════════════════════════════════════════════════════════════════════════

class Toast:
    """One-at-a-time toast attached to a parent window. Call .show(text) to
    flash a message; consecutive calls cancel the prior timeout."""

    def __init__(self, parent: ctk.CTk):
        self._parent = parent
        self._frame: Optional[ctk.CTkFrame] = None
        self._after_id: Optional[str] = None

    def show(self, text: str, *, duration_ms: int = 2200, kind: str = "ok") -> None:
        self._cancel()
        from PIL import Image, ImageDraw, ImageTk

        dot_color = {"ok": theme.SUCCESS, "warn": theme.WARNING,
                     "err": theme.DANGER}.get(kind, theme.SUCCESS)

        try:
            from tkinter.font import Font as _TkFont
            _tw = _TkFont(family=theme.font_family(), size=12).measure(text)
        except Exception:
            _tw = len(text) * 8
        W = _tw + 56
        H = 34
        r = H // 2

        def _hx(c: str) -> tuple:
            c = c.lstrip("#")
            return int(c[:2], 16), int(c[2:4], 16), int(c[4:6], 16)

        # Sentinel color used for corner pixels; made OS-transparent via -transparentcolor.
        # Must not match any real color in the pill content.
        TRANS     = "#020304"
        TRANS_RGB = _hx(TRANS)

        # 1x rendering — no supersampling/LANCZOS resize so corner pixels are
        # exactly TRANS_RGB (no blended intermediate values that would remain visible).
        img = Image.new("RGB", (W, H), TRANS_RGB)
        d = ImageDraw.Draw(img)
        d.rounded_rectangle(
            [0, 0, W - 1, H - 1], radius=r,
            fill=_hx(theme.BG_ELEVATED),
            outline=_hx(theme.BORDER_STRONG),
            width=1,
        )
        photo = ImageTk.PhotoImage(img)

        # Frameless Toplevel: Windows -transparentcolor makes TRANS pixels see-through
        # at the OS compositor level, giving true rounded corners regardless of what
        # content is underneath.
        self._parent.update_idletasks()
        px = self._parent.winfo_rootx()
        py = self._parent.winfo_rooty()
        pw = self._parent.winfo_width()
        ph = self._parent.winfo_height()
        x      = px + (pw - W) // 2
        y_end  = py + ph - 78
        y_start = y_end + 14

        f = tk.Toplevel(self._parent)
        f.overrideredirect(True)
        f.wm_attributes("-topmost", True)
        f.configure(bg=TRANS)
        try:
            f.wm_attributes("-transparentcolor", TRANS)
        except Exception:
            f.configure(bg=theme.BG_BASE)
        f.geometry(f"{W}x{H}+{x}+{y_start}")

        canvas = tk.Canvas(f, width=W, height=H, bg=TRANS, highlightthickness=0, bd=0)
        canvas.pack()
        canvas.create_image(0, 0, anchor="nw", image=photo)
        canvas._photo_ref = photo

        dot_hex = "#{:02x}{:02x}{:02x}".format(*_hx(dot_color))
        cy = H // 2
        canvas.create_oval(14, cy - 4, 22, cy + 4, fill=dot_hex, outline="")
        canvas.create_text(30, cy, text=text, anchor="w",
                           fill=theme.TEXT_1, font=(theme.font_family(), 12))

        def setter(v):
            try:
                f.geometry(f"{W}x{H}+{x}+{int(v)}")
            except Exception:
                pass
        theme.tween(f, setter, y_start, y_end, ms=240, ease=theme.ease_spring)
        self._frame = f
        self._after_id = self._parent.after(duration_ms, self._dismiss)

    def _dismiss(self) -> None:
        f = self._frame
        if f is None:
            return
        try:
            y0 = f.winfo_rooty()
            x0 = f.winfo_rootx()
            W  = f.winfo_width()
            H  = f.winfo_height()
            def setter(v):
                try:
                    f.geometry(f"{W}x{H}+{x0}+{int(v)}")
                except Exception:
                    pass
            theme.tween(f, setter, y0, y0 + 12, ms=180)
            self._parent.after(200, lambda: self._destroy(f))
        except Exception:
            self._destroy(f)
        self._frame = None
        self._after_id = None

    def _destroy(self, frame) -> None:
        try:
            frame.destroy()
        except Exception:
            pass

    def _cancel(self) -> None:
        if self._after_id:
            try:
                self._parent.after_cancel(self._after_id)
            except Exception:
                pass
            self._after_id = None
        if self._frame is not None:
            try:
                self._frame.destroy()
            except Exception:
                pass
            self._frame = None


# ════════════════════════════════════════════════════════════════════════════════
# TabBar — horizontal tabs + sliding accent indicator + content stack
# ════════════════════════════════════════════════════════════════════════════════

class TabBar(ctk.CTkFrame):
    """Custom tab control replacing CTkTabview. Lays out a row of tab buttons
    with an animated accent indicator and a content stack underneath. Each tab
    page is a CTkFrame; only the active page is raised.

    Usage:
        bar = TabBar(parent)
        bar.pack(fill="both", expand=True)
        page1 = bar.add("Bindings", icon="⚡", count=lambda: len(...))
        # populate page1 with widgets...
        bar.select("Bindings")
    """
    BAR_HEIGHT = 38

    def __init__(self, parent, on_change: Callable[[str], None] | None = None, **kw):
        super().__init__(parent, fg_color=theme.BG_BASE, corner_radius=0, **kw)
        self._on_change = on_change
        self._tabs: List[dict] = []        # [{name, button, count_label, count_getter, ...}]
        self._pages: dict[str, ctk.CTkFrame] = {}
        self._active: Optional[str] = None

        # Bar (wraps the tab buttons + indicator canvas)
        self._bar_wrap = ctk.CTkFrame(
            self, fg_color=theme.BG_SURFACE, corner_radius=0, height=self.BAR_HEIGHT + 1,
        )
        self._bar_wrap.pack(side="top", fill="x")
        self._bar_wrap.pack_propagate(False)
        # underline border (1px)
        self._underline = ctk.CTkFrame(
            self, height=1, fg_color=theme.BORDER_SOFT, corner_radius=0,
        )
        self._underline.pack(side="top", fill="x")

        self._bar = ctk.CTkFrame(self._bar_wrap, fg_color="transparent", corner_radius=0)
        self._bar.pack(side="top", fill="x", padx=8)

        # Sliding indicator (canvas overlay)
        self._indicator = tk.Canvas(
            self._bar_wrap, height=2, bg=theme.BG_SURFACE,
            highlightthickness=0, bd=0,
        )
        self._indicator.place(x=0, y=self.BAR_HEIGHT - 2, width=0, height=2)
        self._ind_x = 0.0
        self._ind_w = 0.0

        # Stack
        self._stack = ctk.CTkFrame(self, fg_color=theme.BG_BASE, corner_radius=0)
        self._stack.pack(side="top", fill="both", expand=True)

    def add(self, name: str, *, icon: str = "", count_getter: Callable[[], int] | None = None,
            ) -> ctk.CTkFrame:
        page = ctk.CTkFrame(self._stack, fg_color=theme.BG_BASE, corner_radius=0)
        page.place(relx=0, rely=0, relwidth=1, relheight=1)
        self._pages[name] = page

        btn_frame = ctk.CTkFrame(self._bar, fg_color="transparent", corner_radius=0)
        btn_frame.pack(side="left", padx=0)

        # PIL-rendered SVG-style icon for the design's tab strip.
        from ui.icons import icon as ui_icon
        img_inactive = ui_icon(icon, 13, theme.TEXT_3) if icon else None
        img_hover    = ui_icon(icon, 13, theme.TEXT_2) if icon else None
        img_active   = ui_icon(icon, 13, theme.TEXT_1) if icon else None

        try:
            from tkinter.font import Font as _TkFont
            _tw = _TkFont(family=theme.font_family(), size=12,
                          weight="normal").measure(name)
        except Exception:
            _tw = len(name) * 8
        _iw = 19 if icon else 0   # 13px icon + 6px gap
        btn_width = _tw + _iw + 28  # 14px each side for centered layout

        btn = ctk.CTkButton(
            btn_frame, text=name, image=img_inactive,
            compound="left",
            width=btn_width, height=self.BAR_HEIGHT,
            fg_color="transparent",
            hover_color=theme.BG_SURFACE,   # invisible (matches bar bg)
            text_color=theme.TEXT_3, anchor="center",
            font=theme.font(12, "normal"),
            corner_radius=0,
            command=lambda n=name: self.select(n),
        )
        btn.pack(side="left", padx=(4, 4))

        # Design's .tab:hover { color: var(--text-2); } — only text changes
        # color, never the bg. Bind manually since CTk hover_color is bg-only.
        def _hover_in(_e=None, b=btn, ih=img_hover, ia=img_active, n=name):
            if self._active != n:
                try: b.configure(text_color=theme.TEXT_2, image=ih)
                except Exception: pass
        def _hover_out(_e=None, b=btn, ii=img_inactive, ia=img_active, n=name):
            if self._active != n:
                try: b.configure(text_color=theme.TEXT_3, image=ii)
                except Exception: pass
        btn.bind("<Enter>", _hover_in, add="+")
        btn.bind("<Leave>", _hover_out, add="+")

        count_label = None

        rec = {
            "name": name, "frame": btn_frame, "button": btn,
            "count_label": count_label, "count_getter": count_getter, "page": page,
            "img_active": img_active, "img_inactive": img_inactive,
        }
        self._tabs.append(rec)
        # Auto-select on FIRST add only. Previously every add() queued an
        # `after(50, select(name))` while _active was still None, and they all
        # fired sequentially — last one wins, so Settings ended up active.
        if len(self._tabs) == 1:
            self.after(150, lambda n=name: self.select(n, animate=False))
        self.refresh_counts()
        return page

    def select(self, name: str, *, animate: bool = True) -> None:
        if name not in self._pages or name == self._active:
            if name == self._active:
                return
        prev = self._active
        self._active = name
        # raise the new page
        self._pages[name].tkraise()
        # restyle tab buttons. Keep weight stable across states (design uses 500
        # constantly) — bold-on-active causes layout shift and the design relies
        # on color + indicator + count-pill bg for emphasis.
        for rec in self._tabs:
            is_active = rec["name"] == name
            rec["button"].configure(
                text_color=theme.TEXT_1 if is_active else theme.TEXT_3,
                image=rec["img_active"] if is_active else rec["img_inactive"],
            )
            if rec["count_label"] is not None:
                rec["count_label"].configure(
                    fg_color=theme.ACCENT_BG_2 if is_active else theme.BG_ELEVATED,
                    text_color=theme.ACCENT if is_active else theme.TEXT_2,
                )
        # slide indicator
        self.after(50, lambda: self._move_indicator(name, animate=animate))
        if self._on_change and prev != name:
            try:
                self._on_change(name)
            except Exception:
                pass

    def _move_indicator(self, name: str, *, animate: bool) -> None:
        rec = next((r for r in self._tabs if r["name"] == name), None)
        if rec is None:
            return
        try:
            btn: ctk.CTkButton = rec["button"]
            self.update_idletasks()
            bw = btn.winfo_width()
            if bw <= 1:
                # Layout not ready yet — retry after a short delay
                self.after(60, lambda: self._move_indicator(name, animate=False))
                return
            bx = btn.winfo_rootx() - self._bar_wrap.winfo_rootx()
            x, w = bx, bw
        except Exception:
            return

        if animate and self._ind_w > 0:
            start_x, start_w = self._ind_x, self._ind_w
            def setter_x(v):
                self._ind_x = v
                try: self._indicator.place(x=int(self._ind_x), width=int(self._ind_w))
                except Exception: pass
            def setter_w(v):
                self._ind_w = v
                try: self._indicator.place(x=int(self._ind_x), width=int(self._ind_w))
                except Exception: pass
            theme.tween(self, setter_x, start_x, x, ms=320, ease=theme.ease_out_cubic)
            theme.tween(self, setter_w, start_w, w, ms=320, ease=theme.ease_out_cubic)
        else:
            self._ind_x, self._ind_w = x, w
            try:
                self._indicator.place(x=int(x), width=int(w))
            except Exception:
                pass
        # paint the bar
        self._indicator.delete("all")
        self._indicator.configure(width=int(w))
        self._indicator.create_rectangle(0, 0, max(int(w), 1), 2,
                                         fill=theme.ACCENT, outline="")

    def refresh_counts(self) -> None:
        for rec in self._tabs:
            if rec["count_label"] and rec["count_getter"]:
                try:
                    n = rec["count_getter"]()
                    rec["count_label"].configure(text=str(n))
                except Exception:
                    pass

    def page(self, name: str) -> ctk.CTkFrame:
        return self._pages[name]


# ════════════════════════════════════════════════════════════════════════════════
# Filter chip (planner)
# ════════════════════════════════════════════════════════════════════════════════

class FilterChip(ctk.CTkButton):
    def __init__(self, parent, text: str, on: bool = False,
                 command: Callable[[], None] | None = None,
                 badge: int = 0, badge_kind: str = "danger"):
        self._on = on
        self._badge = badge
        self._badge_kind = badge_kind
        # Auto-size to text + design's `padding: 4px 9px` (18 total horizontal).
        rendered = self._render_text(text)
        try:
            from tkinter.font import Font
            f = Font(family=theme.font_family(), size=10, weight="normal")
            tw = f.measure(rendered)
        except Exception:
            tw = len(rendered) * 7
        super().__init__(
            parent, text=rendered, command=command,
            width=tw + 22, height=24, corner_radius=8,
            fg_color=theme.ACCENT_BG_2 if on else "transparent",
            hover_color=theme.BG_HOVER,
            text_color=theme.ACCENT if on else theme.TEXT_2,
            border_color=theme.ACCENT_BORDER if on else theme.BORDER_SOFT,
            border_width=1,
            font=theme.font(10),
        )
        self._raw_text = text

    def _render_text(self, text: str) -> str:
        if self._badge > 0:
            return f"{text}  {self._badge}"
        return text

    def set_state(self, on: bool, badge: int | None = None) -> None:
        self._on = on
        if badge is not None:
            self._badge = badge
        self.configure(
            text=self._render_text(self._raw_text),
            fg_color=theme.ACCENT_BG_2 if on else "transparent",
            text_color=theme.ACCENT if on else theme.TEXT_2,
            border_color=theme.ACCENT_BORDER if on else theme.BORDER_SOFT,
        )


# ════════════════════════════════════════════════════════════════════════════════
# Action tag (binding action chip)
# ════════════════════════════════════════════════════════════════════════════════

class ActionTag(ctk.CTkFrame):
    def __init__(self, parent, kind: str, value: str | None = None):
        super().__init__(
            parent, fg_color=theme.BG_ELEVATED, corner_radius=5,
            border_color=theme.BORDER_SOFT, border_width=1,
        )
        ctk.CTkLabel(
            self, text=kind, font=theme.font(10),
            text_color=theme.TEXT_3, fg_color="transparent",
        ).pack(side="left", padx=(7, 3), pady=2)
        if value:
            ctk.CTkLabel(
                self, text=value, font=theme.mono(10),
                text_color=theme.TEXT_2, fg_color="transparent",
            ).pack(side="left", padx=(0, 7), pady=2)
        else:
            self.pack_propagate(False)
            self.configure(width=44)
            ctk.CTkFrame(self, fg_color="transparent", width=4).pack(side="left")
