"""
Floating overlay shown while a macro is being recorded.
"""
from __future__ import annotations

import threading
import time
from typing import Callable, Optional

import customtkinter as ctk


class MacroRecordDialog(ctk.CTkToplevel):
    """
    Shows a "Recording…" overlay while the macro recorder runs.
    Calls on_done(json_str | None) when finished.

    Stop strategies:
      • Press Escape (suppressed — won't reach other apps)
      • Click "Stop Recording" button  (last mouse click is automatically removed)
    """

    def __init__(
        self,
        parent: ctk.CTkBaseClass,
        on_done: Callable[[Optional[str]], None],
    ) -> None:
        super().__init__(parent)
        self._on_done = on_done
        self._stop_event = threading.Event()
        self._trim_flag  = [False]   # mutable flag: set True when Stop button pressed
        self._start_time = time.monotonic()

        self.title("Recording Macro")
        self.geometry("340x160")
        self.resizable(False, False)
        self.attributes("-topmost", True)

        self._build()
        self.after(120, self.grab_set)
        self.lift()
        self.focus_force()

        threading.Thread(target=self._record_thread, daemon=True).start()
        self._update_timer()

    # ── layout ────────────────────────────────────────────────────────────────

    def _build(self) -> None:
        ctk.CTkLabel(
            self, text="● Recording…",
            font=ctk.CTkFont(size=16, weight="bold"),
            text_color=("#ff5555", "#ff5555"),
        ).pack(pady=(16, 2))

        self._timer_lbl = ctk.CTkLabel(
            self, text="0.0 s",
            font=ctk.CTkFont(size=24, weight="bold", family="Courier New"),
        )
        self._timer_lbl.pack()

        ctk.CTkLabel(
            self, text="Press  Escape  or click Stop to finish",
            font=ctk.CTkFont(size=11),
            text_color=("#666688", "#666688"),
        ).pack(pady=(4, 6))

        btn_row = ctk.CTkFrame(self, fg_color="transparent")
        btn_row.pack()

        ctk.CTkButton(
            btn_row, text="Stop Recording", width=130, height=30,
            fg_color=("#3a1616", "#3a1616"), hover_color=("#5c2222", "#5c2222"),
            font=ctk.CTkFont(size=12, weight="bold"),
            command=self._stop_clicked,
        ).pack(side="left", padx=4)

        ctk.CTkButton(
            btn_row, text="Cancel", width=80, height=30,
            fg_color=("#252535", "#252535"), hover_color=("#353548", "#353548"),
            font=ctk.CTkFont(size=11),
            command=self._cancel,
        ).pack(side="left", padx=4)

    # ── timer ─────────────────────────────────────────────────────────────────

    def _update_timer(self) -> None:
        if not self.winfo_exists():
            return
        elapsed = time.monotonic() - self._start_time
        self._timer_lbl.configure(text=f"{elapsed:.1f} s")
        self.after(100, self._update_timer)

    # ── recording ─────────────────────────────────────────────────────────────

    def _record_thread(self) -> None:
        from utils.macro_recorder import record_macro
        result = record_macro(
            stop_event=self._stop_event,
            timeout=120.0,
            trim_last_click=self._trim_flag,
        )
        self.after(0, lambda: self._finish(result))

    def _finish(self, result: Optional[str]) -> None:
        if self.winfo_exists():
            self.destroy()
        self._on_done(result)

    def _stop_clicked(self) -> None:
        """Stop button: mark that the click should be trimmed, then stop."""
        self._trim_flag[0] = True
        self._stop_event.set()

    def _cancel(self) -> None:
        """Cancel: stop and discard everything."""
        self._stop_event.set()
        self.after(200, lambda: self._finish(None))
