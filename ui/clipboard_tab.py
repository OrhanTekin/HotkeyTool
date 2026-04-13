"""
Clipboard tab: scrollable history of the last 20 clipboard entries.

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

_POLL_MS = 500


class ClipboardTab(ctk.CTkFrame):
    def __init__(self, parent: ctk.CTkBaseClass, app: "App") -> None:
        super().__init__(parent, fg_color="transparent")
        self.app = app
        self._buttons: list[ctk.CTkButton] = []
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
            text="Clipboard history is empty.\nCopy some text to see it here.",
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
                try:
                    text = self.clipboard_get()   # tkinter — has message queue
                except Exception:
                    text = None
                if text and text.strip():
                    # Skip if this is text we wrote ourselves via copy_item
                    if text == self._suppress_text:
                        self._suppress_text = ""
                    else:
                        self.app.clipboard.add(text)
        except Exception:
            pass
        self.after(_POLL_MS, self._poll)

    # ── history display ───────────────────────────────────────────────────────

    def _on_history_change(self, _history) -> None:
        """Callback fired by ClipboardManager.add() — already on main thread."""
        self.refresh()

    def refresh(self) -> None:
        for btn in self._buttons:
            btn.destroy()
        self._buttons.clear()

        history = self.app.clipboard.history
        if not history:
            self._empty.pack(pady=48)
            return

        self._empty.pack_forget()
        for i, text in enumerate(history):
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

    def _copy(self, text: str) -> None:
        # Write via tkinter (main thread, has message queue — works reliably)
        self.clipboard_clear()
        self.clipboard_append(text)
        # Capture new seq so the next poll doesn't re-add this entry
        self._last_seq = ctypes.windll.user32.GetClipboardSequenceNumber()
        self._suppress_text = text
        # Move entry to top of history
        self.app.clipboard.add(text)
        if self.app.window:
            self.app.window.update_status(f"Copied to clipboard: {text[:40]}")

    def _clear(self) -> None:
        self.app.clipboard.clear_history()
        self.refresh()
