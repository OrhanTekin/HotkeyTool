"""
Clipboard tab: scrollable history of the last 20 text entries and up to
5 image thumbnails.

Polling runs entirely on the main (Tkinter) thread via self.after().
clipboard_get() uses Tkinter's own clipboard bridge which has a message queue,
so it works with apps that use delayed clipboard rendering (Chrome, Edge, …).
"""
from __future__ import annotations

import ctypes
import time
from typing import TYPE_CHECKING

import customtkinter as ctk

from ui import theme
from ui.widgets import DangerButton, GhostButton

if TYPE_CHECKING:
    from app import App

_POLL_MS    = 500
_MAX_IMAGES = 5
_THUMB_W    = 80
_THUMB_H    = 50

_CF_UNICODETEXT = 13
_CF_DIB         = 8
_CF_DIBV5       = 17


class ClipboardTab(ctk.CTkFrame):
    def __init__(self, parent: ctk.CTkBaseClass, app: "App") -> None:
        super().__init__(parent, fg_color=theme.BG_BASE)
        self.app = app
        self._buttons: list = []
        self._image_history: list = []
        self._image_widgets:  list = []
        self._ctk_images:     list = []
        self._timestamps: dict = {}     # id(text) → time.time() of insert
        self._last_seq: int = ctypes.windll.user32.GetClipboardSequenceNumber()
        self._suppress_text: str = ""
        self._build()
        self.app.clipboard.set_callback(self._on_history_change)
        self.after(_POLL_MS, self._poll)

    def _build(self) -> None:
        tb = ctk.CTkFrame(self, fg_color="transparent", height=58)
        tb.pack(fill="x", padx=18, pady=(14, 8))
        tb.pack_propagate(False)

        ctk.CTkLabel(
            tb, text="Clipboard History",
            font=theme.font(13, "bold"),
            text_color=theme.TEXT_1, fg_color="transparent",
        ).pack(side="left")

        ctk.CTkLabel(
            tb, text="Click any entry to copy it back.",
            font=theme.font(11), text_color=theme.TEXT_3, fg_color="transparent",
        ).pack(side="left", padx=(12, 0))

        DangerButton(tb, text="Clear all", small=True, command=self._clear
                     ).pack(side="right")

        ctk.CTkFrame(self, height=1, fg_color=theme.BORDER_SOFT, corner_radius=0
                     ).pack(fill="x")

        self._scroll = ctk.CTkScrollableFrame(
            self, fg_color=theme.BG_BASE,
            scrollbar_button_color=theme.BG_ELEVATED,
            scrollbar_button_hover_color=theme.BORDER_STRONG,
        )
        self._scroll.pack(fill="both", expand=True, padx=10, pady=(8, 8))

        self._empty = ctk.CTkFrame(self._scroll, fg_color="transparent")
        ctk.CTkLabel(
            self._empty, text="📋",
            font=theme.font(28), text_color=theme.TEXT_3, fg_color=theme.BG_ELEVATED,
            width=56, height=56, corner_radius=14,
        ).pack(pady=(0, 14))
        ctk.CTkLabel(
            self._empty, text="Clipboard is empty",
            font=theme.font(14, "bold"), text_color=theme.TEXT_1,
        ).pack()
        ctk.CTkLabel(
            self._empty,
            text="Anything you copy will appear here automatically — text or images.",
            font=theme.font(12), text_color=theme.TEXT_3, wraplength=320, justify="center",
        ).pack(pady=(4, 0))

        self.refresh()

    # ── polling (main thread) ─────────────────────────────────────────────────

    def _poll(self) -> None:
        if not self.winfo_exists():
            return
        try:
            seq = ctypes.windll.user32.GetClipboardSequenceNumber()
            if seq != self._last_seq:
                self._last_seq = seq
                self._capture_clipboard()
        except Exception:
            pass
        self.after(_POLL_MS, self._poll)

    def _capture_clipboard(self) -> None:
        user32 = ctypes.windll.user32

        try:
            text = self.clipboard_get()
        except Exception:
            text = None

        if text and text.strip():
            if text == self._suppress_text:
                self._suppress_text = ""
            else:
                self.app.clipboard.add(text)
                self._timestamps[text] = time.time()
            return

        has_image = (
            user32.IsClipboardFormatAvailable(_CF_DIBV5) or
            user32.IsClipboardFormatAvailable(_CF_DIB)
        )
        if not has_image:
            return
        try:
            from PIL import ImageGrab
            img = ImageGrab.grabclipboard()
        except Exception:
            return
        if img is None:
            return

        sig = (img.size, img.mode, img.tobytes()[:512])
        if any(
            (x.size, x.mode, x.tobytes()[:512]) == sig
            for x in self._image_history
        ):
            return

        self._image_history.insert(0, img)
        if len(self._image_history) > _MAX_IMAGES:
            self._image_history = self._image_history[:_MAX_IMAGES]
        self.refresh()

    # ── history display ───────────────────────────────────────────────────────

    def _on_history_change(self, _history) -> None:
        self.refresh()

    def refresh(self) -> None:
        for btn in self._buttons:
            try: btn.destroy()
            except Exception: pass
        self._buttons.clear()
        for row in self._image_widgets:
            try: row.destroy()
            except Exception: pass
        self._image_widgets.clear()
        self._ctk_images.clear()

        text_history  = self.app.clipboard.history
        image_history = self._image_history

        if not text_history and not image_history:
            self._empty.pack(pady=60)
            return

        self._empty.pack_forget()

        for img in image_history:
            self._add_image_row(img)

        for text in text_history:
            self._add_text_row(text)

    def _add_text_row(self, text: str) -> None:
        item = _ClipItem(self._scroll, kind="text", text=text,
                         when=self._fmt_when(text),
                         on_click=lambda t=text: self._copy(t))
        item.pack(fill="x", pady=(0, 6), padx=2)
        self._buttons.append(item)

    def _add_image_row(self, img) -> None:
        try:
            from PIL import Image

            thumb = img.copy()
            thumb.thumbnail((_THUMB_W, _THUMB_H), Image.LANCZOS)

            ctk_img = ctk.CTkImage(light_image=thumb, dark_image=thumb, size=thumb.size)
            self._ctk_images.append(ctk_img)

            item = _ClipItem(
                self._scroll, kind="image",
                text=f"Screenshot · {img.width} × {img.height}",
                when="just now",
                on_click=lambda: self._copy_image(img),
                image=ctk_img,
                on_remove=lambda: self._remove_image(img),
            )
            item.pack(fill="x", pady=(0, 6), padx=2)
            self._image_widgets.append(item)
        except Exception as exc:
            print(f"[HotkeyTool] Clipboard image display error: {exc}")

    def _fmt_when(self, text: str) -> str:
        ts = self._timestamps.get(text)
        if ts is None:
            return ""
        d = time.time() - ts
        if d < 60: return "just now"
        if d < 3600: return f"{int(d / 60)} min ago"
        if d < 86400: return f"{int(d / 3600)} hr ago"
        return f"{int(d / 86400)} d ago"

    # ── actions ───────────────────────────────────────────────────────────────

    def _copy(self, text: str) -> None:
        self.clipboard_clear()
        self.clipboard_append(text)
        self._last_seq = ctypes.windll.user32.GetClipboardSequenceNumber()
        self._suppress_text = text
        self.app.clipboard.add(text)
        if self.app.window:
            self.app.window.toast("Copied to clipboard")

    def _copy_image(self, img) -> None:
        try:
            import io
            from PIL import Image
            output = io.BytesIO()
            img.convert("RGB").save(output, format="BMP")
            bmp_data = output.getvalue()
            dib_data = bmp_data[14:]

            user32   = ctypes.windll.user32
            kernel32 = ctypes.windll.kernel32
            kernel32.GlobalAlloc.restype  = ctypes.c_void_p
            kernel32.GlobalAlloc.argtypes = [ctypes.c_uint, ctypes.c_size_t]
            kernel32.GlobalLock.restype   = ctypes.c_void_p
            kernel32.GlobalLock.argtypes  = [ctypes.c_void_p]
            kernel32.GlobalUnlock.argtypes = [ctypes.c_void_p]
            GMEM_MOVEABLE = 0x0002

            h = kernel32.GlobalAlloc(GMEM_MOVEABLE, len(dib_data))
            p = kernel32.GlobalLock(h)
            ctypes.memmove(p, dib_data, len(dib_data))
            kernel32.GlobalUnlock(h)

            if user32.OpenClipboard(None):
                user32.EmptyClipboard()
                user32.SetClipboardData(_CF_DIB, ctypes.c_void_p(h))
                user32.CloseClipboard()
                self._last_seq = user32.GetClipboardSequenceNumber()

            if self.app.window:
                self.app.window.toast(f"Image copied · {img.width}×{img.height}")
        except Exception as exc:
            print(f"[HotkeyTool] Image copy error: {exc}")

    def _remove_image(self, img) -> None:
        if img in self._image_history:
            self._image_history.remove(img)
        self.refresh()

    def _clear(self) -> None:
        self._image_history.clear()
        self.app.clipboard.clear_history()
        self.refresh()
        if self.app.window:
            self.app.window.toast("History cleared")


class _ClipItem(ctk.CTkFrame):
    """Clip-item row matching design's .clip-item — kind badge + text + when."""
    def __init__(self, parent, *, kind: str, text: str, when: str,
                 on_click, image=None, on_remove=None):
        super().__init__(
            parent, fg_color=theme.BG_ROW, corner_radius=10,
            border_color=theme.BORDER_SOFT, border_width=1, height=54,
        )
        self.pack_propagate(False)
        self._on_click = on_click

        if image is not None:
            ctk.CTkLabel(self, image=image, text="", fg_color="transparent",
                         ).pack(side="left", padx=10, pady=8)

        # kind badge
        kind_bg = theme.BG_ELEVATED
        kind_fg = theme.PURPLE if kind == "image" else theme.TEXT_3
        ctk.CTkLabel(
            self, text=kind.upper(),
            font=theme.font(9, "bold"),
            fg_color=kind_bg, corner_radius=4,
            text_color=kind_fg,
            padx=6, pady=2,
        ).pack(side="left", padx=(10 if image is None else 4, 8), pady=10)

        # text (truncated)
        preview = text.replace("\n", " ").replace("\r", "")
        if len(preview) > 110:
            preview = preview[:110] + "…"
        text_label = ctk.CTkLabel(
            self, text=preview, anchor="w",
            font=theme.font(12),
            text_color=theme.TEXT_1, fg_color="transparent",
        )
        text_label.pack(side="left", fill="x", expand=True, padx=4, pady=10)

        if when:
            ctk.CTkLabel(
                self, text=when,
                font=theme.font(11),
                text_color=theme.TEXT_4, fg_color="transparent",
            ).pack(side="right", padx=(8, 12), pady=10)

        if on_remove:
            DangerButton(self, text="Remove", small=True, command=on_remove
                         ).pack(side="right", padx=(0, 8), pady=10)

        # Whole-row click handler
        for w in (self, text_label):
            w.bind("<Button-1>", lambda _e: self._invoke())
            try: w.configure(cursor="hand2")
            except Exception: pass
        self.bind("<Enter>", lambda _e: self.configure(fg_color=theme.BG_HOVER, border_color=theme.ACCENT_BORDER))
        self.bind("<Leave>", lambda _e: self.configure(fg_color=theme.BG_ROW, border_color=theme.BORDER_SOFT))

    def _invoke(self) -> None:
        try:
            self._on_click()
        except Exception:
            pass
