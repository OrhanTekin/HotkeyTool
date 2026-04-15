"""
Clipboard tab: scrollable history of the last 20 text entries and up to
5 image thumbnails.

Polling runs entirely on the main (Tkinter) thread via self.after().
clipboard_get() uses Tkinter's own clipboard bridge which has a message queue,
so it works with apps that use delayed clipboard rendering (Chrome, Edge, …).
"""
from __future__ import annotations

import ctypes
from typing import TYPE_CHECKING

import customtkinter as ctk

if TYPE_CHECKING:
    from app import App

_POLL_MS    = 500
_MAX_IMAGES = 5
_THUMB_W    = 160
_THUMB_H    = 100

# Windows clipboard format IDs
_CF_UNICODETEXT = 13
_CF_DIB         = 8
_CF_DIBV5       = 17


class ClipboardTab(ctk.CTkFrame):
    def __init__(self, parent: ctk.CTkBaseClass, app: "App") -> None:
        super().__init__(parent, fg_color="transparent")
        self.app = app
        self._buttons: list[ctk.CTkButton] = []
        self._image_history: list = []      # PIL Image objects
        self._image_widgets:  list = []     # CTkFrame rows (keep refs to avoid GC)
        self._ctk_images:     list = []     # CTkImage refs (prevent GC)
        # Initialise to the current sequence number so the first poll doesn't
        # immediately capture whatever happens to be in the clipboard right now.
        self._last_seq: int = ctypes.windll.user32.GetClipboardSequenceNumber()
        self._suppress_text: str = ""   # text written by copy_item — skip once
        self._build()
        self.app.clipboard.set_callback(self._on_history_change)
        # Start the polling loop once the widget is mapped
        self.after(_POLL_MS, self._poll)

    def _build(self) -> None:
        tb = ctk.CTkFrame(self, fg_color="transparent", height=50)
        tb.pack(fill="x", padx=4, pady=(4, 0))
        tb.pack_propagate(False)

        ctk.CTkLabel(
            tb, text="Clipboard History",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color=("#99aacc", "#99aacc"),
        ).pack(side="left", padx=4)

        ctk.CTkButton(
            tb, text="Clear History", width=110, height=32,
            fg_color=("#5c1a1a", "#5c1a1a"), hover_color=("#7a2222", "#7a2222"),
            font=ctk.CTkFont(size=11),
            command=self._clear,
        ).pack(side="right", padx=4)

        ctk.CTkLabel(
            tb,
            text="Click any entry to copy it back to clipboard",
            font=ctk.CTkFont(size=11),
            text_color=("#555577", "#555577"),
        ).pack(side="left", padx=8)

        self._scroll = ctk.CTkScrollableFrame(self, fg_color="transparent")
        self._scroll.pack(fill="both", expand=True, padx=4, pady=(4, 4))

        self._empty = ctk.CTkLabel(
            self._scroll,
            text="Clipboard history is empty.\nCopy some text or an image to see it here.",
            font=ctk.CTkFont(size=14),
            text_color=("#444466", "#444466"),
            justify="center",
        )

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

        # ── try text first ──
        try:
            text = self.clipboard_get()   # tkinter — has message queue
        except Exception:
            text = None

        if text and text.strip():
            if text == self._suppress_text:
                self._suppress_text = ""
            else:
                self.app.clipboard.add(text)
            return   # text wins; don't also store as image

        # ── try image ──
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

        # Keep only the last _MAX_IMAGES unique images (compare by size + mode as a cheap hash)
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
        """Callback fired by ClipboardManager.add() — already on main thread."""
        self.refresh()

    def refresh(self) -> None:
        # Destroy previous widgets
        for btn in self._buttons:
            try:
                btn.destroy()
            except Exception:
                pass
        self._buttons.clear()
        for row in self._image_widgets:
            try:
                row.destroy()
            except Exception:
                pass
        self._image_widgets.clear()
        self._ctk_images.clear()

        text_history  = self.app.clipboard.history
        image_history = self._image_history

        if not text_history and not image_history:
            self._empty.pack(pady=48)
            return

        self._empty.pack_forget()

        # ── images first ──
        for img in image_history:
            self._add_image_row(img)

        # ── text entries ──
        for i, text in enumerate(text_history):
            preview = text.replace("\n", " ").replace("\r", "")
            if len(preview) > 100:
                preview = preview[:97] + "…"

            bg = ("#1a1a2e", "#1a1a2e") if i % 2 == 0 else ("#16162a", "#16162a")
            btn = ctk.CTkButton(
                self._scroll,
                text=f"  {preview}",
                anchor="w",
                height=34,
                fg_color=bg,
                hover_color=("#252545", "#252545"),
                text_color=("#d0d0ee", "#d0d0ee"),
                font=ctk.CTkFont(size=12),
                command=lambda t=text: self._copy(t),
            )
            btn.pack(fill="x", pady=(0, 2))
            self._buttons.append(btn)

    def _add_image_row(self, img) -> None:
        """Add a thumbnail row for a PIL Image."""
        try:
            from PIL import Image

            thumb = img.copy()
            thumb.thumbnail((_THUMB_W, _THUMB_H), Image.LANCZOS)

            ctk_img = ctk.CTkImage(light_image=thumb, dark_image=thumb,
                                   size=thumb.size)
            self._ctk_images.append(ctk_img)

            row = ctk.CTkFrame(self._scroll, fg_color=("#1a1a2e", "#1a1a2e"),
                               corner_radius=6)
            row.pack(fill="x", pady=(0, 4))
            self._image_widgets.append(row)

            lbl = ctk.CTkLabel(row, image=ctk_img, text="")
            lbl.pack(side="left", padx=8, pady=6)

            info = ctk.CTkLabel(
                row,
                text=f"Image  {img.width} × {img.height}",
                font=ctk.CTkFont(size=11),
                text_color=("#888899", "#888899"),
            )
            info.pack(side="left", padx=4)

            ctk.CTkButton(
                row, text="Copy", width=70, height=26,
                font=ctk.CTkFont(size=11),
                fg_color=("#1e3a2a", "#1e3a2a"), hover_color=("#2a5038", "#2a5038"),
                command=lambda i=img: self._copy_image(i),
            ).pack(side="right", padx=8, pady=6)

            ctk.CTkButton(
                row, text="Remove", width=76, height=26,
                font=ctk.CTkFont(size=11),
                fg_color=("#3a1616", "#3a1616"), hover_color=("#5c2222", "#5c2222"),
                command=lambda i=img: self._remove_image(i),
            ).pack(side="right", padx=(0, 4), pady=6)

        except Exception as exc:
            print(f"[HotkeyTool] Clipboard image display error: {exc}")

    # ── actions ───────────────────────────────────────────────────────────────

    def _copy(self, text: str) -> None:
        self.clipboard_clear()
        self.clipboard_append(text)
        self._last_seq = ctypes.windll.user32.GetClipboardSequenceNumber()
        self._suppress_text = text
        self.app.clipboard.add(text)
        if self.app.window:
            self.app.window.update_status(f"Copied to clipboard: {text[:40]}")

    def _copy_image(self, img) -> None:
        """Copy a PIL Image back to the Windows clipboard."""
        try:
            import io
            from PIL import Image
            # Write as CF_DIB via Win32
            output = io.BytesIO()
            img.convert("RGB").save(output, format="BMP")
            bmp_data = output.getvalue()
            # BMP file header is 14 bytes; CF_DIB starts at the info header
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
                self.app.window.update_status(
                    f"Image copied  ({img.width}×{img.height})"
                )
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
