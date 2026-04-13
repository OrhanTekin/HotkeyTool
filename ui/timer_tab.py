"""
Timer tab: one or more countdown timers with popup notification when finished.
"""
from __future__ import annotations

import threading
import time
from typing import TYPE_CHECKING

import customtkinter as ctk

if TYPE_CHECKING:
    from app import App


class TimerTab(ctk.CTkFrame):
    def __init__(self, parent: ctk.CTkBaseClass, app: "App") -> None:
        super().__init__(parent, fg_color="transparent")
        self.app = app
        self._timers: list[_TimerCard] = []
        self._build()

    def _build(self) -> None:
        tb = ctk.CTkFrame(self, fg_color="transparent", height=50)
        tb.pack(fill="x", padx=4, pady=(4, 0))
        tb.pack_propagate(False)

        ctk.CTkButton(
            tb, text="+ Add Timer",
            width=130, height=36,
            font=ctk.CTkFont(size=13, weight="bold"),
            command=self._add_timer,
        ).pack(side="left")

        ctk.CTkLabel(
            tb,
            text="A popup appears when a timer reaches zero",
            font=ctk.CTkFont(size=11),
            text_color=("#555577", "#555577"),
        ).pack(side="left", padx=10)

        self._scroll = ctk.CTkScrollableFrame(self, fg_color="transparent")
        self._scroll.pack(fill="both", expand=True, padx=4, pady=(8, 4))

        self._empty = ctk.CTkLabel(
            self._scroll,
            text='No timers.\nClick "+ Add Timer" to create one.',
            font=ctk.CTkFont(size=14),
            text_color=("#444466", "#444466"),
            justify="center",
        )
        self._empty.pack(pady=48)

        # Add a default timer on first open
        self._add_timer()

    def _add_timer(self) -> None:
        self._empty.pack_forget()
        card = _TimerCard(self._scroll, self)
        card.pack(fill="x", pady=(0, 8))
        self._timers.append(card)

    def remove_timer(self, card: "_TimerCard") -> None:
        card.destroy()
        if card in self._timers:
            self._timers.remove(card)
        if not self._timers:
            self._empty.pack(pady=48)

    def notify(self, label: str) -> None:
        """Called from a timer thread when countdown finishes."""
        if self.winfo_exists():
            self.after(0, lambda: self._show_popup(label))

    def _show_popup(self, label: str) -> None:
        win = _TimerPopup(self, label)
        win.lift()


class _TimerCard(ctk.CTkFrame):
    _STATES = ("idle", "running", "paused", "done")

    def __init__(self, parent, tab: TimerTab) -> None:
        super().__init__(parent, fg_color=("#1a1a2e", "#1a1a2e"), corner_radius=10)
        self.tab = tab
        self._remaining: float = 0.0
        self._state = "idle"
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._build()

    def _build(self) -> None:
        top = ctk.CTkFrame(self, fg_color="transparent")
        top.pack(fill="x", padx=12, pady=(10, 4))

        ctk.CTkLabel(top, text="Label:", font=ctk.CTkFont(size=12)).pack(side="left")
        self._label_var = ctk.StringVar(value="Timer")
        ctk.CTkEntry(top, textvariable=self._label_var, width=160, height=26).pack(side="left", padx=4)

        ctk.CTkButton(
            top, text="✕", width=24, height=24,
            fg_color="transparent", hover_color=("#5c1a1a","#5c1a1a"),
            font=ctk.CTkFont(size=12),
            command=lambda: self.tab.remove_timer(self),
        ).pack(side="right")

        # Duration inputs
        dur = ctk.CTkFrame(self, fg_color="transparent")
        dur.pack(fill="x", padx=12, pady=2)

        for attr, label, default in [
            ("_h_var",  "h",  "0"),
            ("_m_var",  "m",  "5"),
            ("_s_var",  "s",  "0"),
        ]:
            v = ctk.StringVar(value=default)
            setattr(self, attr, v)
            ctk.CTkEntry(dur, textvariable=v, width=52, height=30,
                         font=ctk.CTkFont(size=14, weight="bold"),
                         justify="center").pack(side="left", padx=2)
            ctk.CTkLabel(dur, text=label,
                         font=ctk.CTkFont(size=12),
                         text_color=("#666688","#666688")).pack(side="left", padx=(0, 6))

        # Display + controls
        ctrl = ctk.CTkFrame(self, fg_color="transparent")
        ctrl.pack(fill="x", padx=12, pady=(4, 10))

        self._display = ctk.CTkLabel(
            ctrl, text="00:05:00",
            font=ctk.CTkFont(size=22, weight="bold", family="Courier New"),
            text_color=("#88ccff", "#88ccff"),
            width=140,
        )
        self._display.pack(side="left")

        self._start_btn = ctk.CTkButton(
            ctrl, text="Start", width=70, height=30,
            fg_color=("#163a22","#163a22"), hover_color=("#1e4a2a","#1e4a2a"),
            font=ctk.CTkFont(size=12, weight="bold"),
            command=self._start,
        )
        self._start_btn.pack(side="left", padx=(8, 2))

        self._pause_btn = ctk.CTkButton(
            ctrl, text="Pause", width=65, height=30,
            fg_color=("#1e2a3a","#1e2a3a"), hover_color=("#2a3a4a","#2a3a4a"),
            font=ctk.CTkFont(size=12), state="disabled",
            command=self._pause,
        )
        self._pause_btn.pack(side="left", padx=2)

        ctk.CTkButton(
            ctrl, text="Reset", width=60, height=30,
            fg_color=("#3a1616","#3a1616"), hover_color=("#5c2222","#5c2222"),
            font=ctk.CTkFont(size=12),
            command=self._reset,
        ).pack(side="left", padx=2)

    def _total_seconds(self) -> int:
        try:
            h = int(self._h_var.get())
            m = int(self._m_var.get())
            s = int(self._s_var.get())
            return h * 3600 + m * 60 + s
        except Exception:
            return 0

    def _format(self, secs: float) -> str:
        s = int(secs)
        h, rem = divmod(s, 3600)
        m, sec = divmod(rem, 60)
        return f"{h:02d}:{m:02d}:{sec:02d}"

    def _start(self) -> None:
        if self._state == "idle":
            total = self._total_seconds()
            if total <= 0:
                return
            self._remaining = float(total)
        elif self._state == "paused":
            pass  # resume
        else:
            return

        self._state = "running"
        self._start_btn.configure(state="disabled")
        self._pause_btn.configure(state="normal")
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def _pause(self) -> None:
        if self._state == "running":
            self._state = "paused"
            self._stop_event.set()
            self._start_btn.configure(text="Resume", state="normal")
            self._pause_btn.configure(state="disabled")

    def _reset(self) -> None:
        self._state = "idle"
        self._stop_event.set()
        total = self._total_seconds()
        self._remaining = float(total)
        if self.winfo_exists():
            self._display.configure(text=self._format(total),
                                    text_color=("#88ccff", "#88ccff"))
            self._start_btn.configure(text="Start", state="normal")
            self._pause_btn.configure(state="disabled")

    def _run(self) -> None:
        while self._remaining > 0 and not self._stop_event.is_set():
            time.sleep(0.5)
            if self._stop_event.is_set():
                break
            self._remaining = max(0.0, self._remaining - 0.5)
            if self.winfo_exists():
                self.after(0, self._update_display)

        if self._remaining <= 0 and not self._stop_event.is_set():
            self._state = "done"
            if self.winfo_exists():
                self.after(0, self._on_done)

    def _update_display(self) -> None:
        if self.winfo_exists():
            self._display.configure(text=self._format(self._remaining))

    def _on_done(self) -> None:
        if self.winfo_exists():
            self._display.configure(text="00:00:00",
                                    text_color=("#ff5555", "#ff5555"))
            self._start_btn.configure(state="disabled")
            self._pause_btn.configure(state="disabled")
        self.tab.notify(self._label_var.get())


class _TimerPopup(ctk.CTkToplevel):
    def __init__(self, parent, label: str) -> None:
        super().__init__(parent)
        self.title("Timer Finished")
        self.geometry("340x160")
        self.resizable(False, False)
        self.attributes("-topmost", True)

        ctk.CTkLabel(
            self, text="⏰  Timer Finished!",
            font=ctk.CTkFont(size=18, weight="bold"),
            text_color=("#ffaa55", "#ffaa55"),
        ).pack(pady=(24, 6))

        ctk.CTkLabel(
            self, text=label,
            font=ctk.CTkFont(size=14),
        ).pack()

        ctk.CTkButton(
            self, text="OK", width=100, height=34,
            font=ctk.CTkFont(size=13, weight="bold"),
            command=self.destroy,
        ).pack(pady=(16, 0))

        self.after(120, self.grab_set)
        self.lift()
        self.focus_force()
