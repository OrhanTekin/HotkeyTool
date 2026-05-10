"""
Timer tab: one or more countdown timers with popup notification when finished.
"""
from __future__ import annotations

import threading
import time
from typing import TYPE_CHECKING

import customtkinter as ctk

from core.models import SavedTimer
from ui import theme
from ui.widgets import (
    DangerButton, GhostButton, IconButton, PrimaryButton, SuccessButton,
)

if TYPE_CHECKING:
    from app import App


class TimerTab(ctk.CTkFrame):
    def __init__(self, parent: ctk.CTkBaseClass, app: "App") -> None:
        super().__init__(parent, fg_color=theme.BG_BASE)
        self.app = app
        self._timers: list[_TimerCard] = []
        self._build()

    def _build(self) -> None:
        tb = ctk.CTkFrame(self, fg_color="transparent", height=58)
        tb.pack(fill="x", padx=18, pady=(14, 8))
        tb.pack_propagate(False)

        PrimaryButton(tb, text="+  Add Timer", command=self._add_timer).pack(side="left")

        ctk.CTkLabel(
            tb, text="A popup appears when a timer reaches zero.",
            font=theme.font(11), text_color=theme.TEXT_3, fg_color="transparent",
        ).pack(side="left", padx=(12, 0))

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
            self._empty, text="⏱",
            font=theme.font(28), text_color=theme.TEXT_3, fg_color=theme.BG_ELEVATED,
            width=56, height=56, corner_radius=14,
        ).pack(pady=(0, 14))
        ctk.CTkLabel(
            self._empty, text="No timers",
            font=theme.font(14, "bold"), text_color=theme.TEXT_1,
        ).pack()

        # Load saved timers; create default if none saved yet
        saved = self.app.config.timers
        if not saved:
            st = SavedTimer.new()
            self.app.config.timers.append(st)
            self.app.save_config_only()
            saved = [st]

        for st in saved:
            card = _TimerCard(self._scroll, self, st)
            card.pack(fill="x", pady=(0, 10))
            self._timers.append(card)

    def _add_timer(self) -> None:
        self._empty.pack_forget()
        st = SavedTimer.new()
        self.app.config.timers.append(st)
        self.app.save_config_only()
        card = _TimerCard(self._scroll, self, st)
        card.pack(fill="x", pady=(0, 10))
        self._timers.append(card)

    def remove_timer(self, card: "_TimerCard") -> None:
        try:
            self.app.config.timers.remove(card.saved_timer)
        except ValueError:
            pass
        self.app.save_config_only()
        card.destroy()
        if card in self._timers:
            self._timers.remove(card)
        if not self._timers:
            self._empty.pack(pady=60)

    def notify(self, label: str) -> None:
        if self.winfo_exists():
            self.after(0, lambda: self._show_popup(label))

    def _show_popup(self, label: str) -> None:
        win = _TimerPopup(self, label)
        win.lift()


class _TimerCard(ctk.CTkFrame):
    _STATES = ("idle", "running", "paused", "done")

    def __init__(self, parent, tab: TimerTab, saved_timer: SavedTimer) -> None:
        super().__init__(
            parent, fg_color=theme.BG_ELEVATED, corner_radius=14,
            border_color=theme.BORDER_SOFT, border_width=1,
        )
        self.tab = tab
        self.saved_timer = saved_timer
        self._remaining: float = 0.0
        self._total: float = 300.0
        self._state = "idle"
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._build()
        self._bind_save()
        self._tick_progress()

    def _build(self) -> None:
        st = self.saved_timer
        total_secs = st.hours * 3600 + st.minutes * 60 + st.seconds
        if total_secs <= 0:
            total_secs = 300
        self._total = float(total_secs)
        self._remaining = self._total

        # Two-column grid: label/inputs/digits left, controls right
        body = ctk.CTkFrame(self, fg_color="transparent")
        body.pack(fill="x", padx=18, pady=18)

        # ── left column ──
        left = ctk.CTkFrame(body, fg_color="transparent")
        left.pack(side="left", fill="x", expand=True)

        label_row = ctk.CTkFrame(left, fg_color="transparent")
        label_row.pack(anchor="w", fill="x")

        self._label_var = ctk.StringVar(value=st.label)
        ctk.CTkEntry(
            label_row, textvariable=self._label_var, width=180, height=28,
            font=theme.font(12),
            fg_color=theme.BG_INPUT, text_color=theme.TEXT_1,
            border_color=theme.BORDER, border_width=1,
            placeholder_text="Label",
        ).pack(side="left")

        self._state_label = ctk.CTkLabel(
            label_row, text="· IDLE",
            font=theme.font(10, "bold"),
            text_color=theme.TEXT_4, fg_color="transparent",
        )
        self._state_label.pack(side="left", padx=(8, 0))

        # Duration inputs row
        dur = ctk.CTkFrame(left, fg_color="transparent")
        dur.pack(anchor="w", pady=(8, 8))

        for attr, default in [("_h_var", str(st.hours)),
                               ("_m_var", str(st.minutes)),
                               ("_s_var", str(st.seconds))]:
            v = ctk.StringVar(value=default)
            setattr(self, attr, v)
            ctk.CTkEntry(
                dur, textvariable=v, width=42, height=26,
                font=theme.mono(12, "bold"),
                fg_color=theme.BG_INPUT, text_color=theme.TEXT_1,
                border_color=theme.BORDER, border_width=1,
                justify="center",
            ).pack(side="left", padx=(0, 2))
            label = "h" if attr == "_h_var" else ("m" if attr == "_m_var" else "s")
            ctk.CTkLabel(
                dur, text=label, font=theme.font(11),
                text_color=theme.TEXT_3, fg_color="transparent",
            ).pack(side="left", padx=(0, 8))

        # Big digits
        self._display = ctk.CTkLabel(
            left, text=self._format(self._total),
            font=theme.mono(38, "bold"),
            text_color=theme.TEXT_1, fg_color="transparent",
        )
        self._display.pack(anchor="w", pady=(2, 0))

        # ── right column ──
        ctrl = ctk.CTkFrame(body, fg_color="transparent")
        ctrl.pack(side="right", padx=(20, 0))

        self._start_btn = SuccessButton(ctrl, text="Start", small=True, command=self._start)
        self._start_btn.pack(side="left", padx=2)

        self._pause_btn = GhostButton(ctrl, text="Pause", small=True, command=self._pause)
        self._pause_btn.pack(side="left", padx=2)
        self._pause_btn.configure(state="disabled")

        GhostButton(ctrl, text="Reset", small=True, command=self._reset
                    ).pack(side="left", padx=2)

        IconButton(ctrl, "✕", kind="danger", size=26,
                   command=lambda: self.tab.remove_timer(self)
                   ).pack(side="left", padx=(8, 0))

        # Bottom progress bar
        self._progress = ctk.CTkFrame(
            self, height=2, fg_color=theme.ACCENT, corner_radius=0, width=1,
        )
        self._progress.place(x=0, rely=1.0, y=-2)

    def _bind_save(self) -> None:
        def _on_change(*_):
            self.saved_timer.label = self._label_var.get()
            try:
                self.saved_timer.hours   = int(self._h_var.get() or "0")
                self.saved_timer.minutes = int(self._m_var.get() or "0")
                self.saved_timer.seconds = int(self._s_var.get() or "0")
            except ValueError:
                pass
            self.tab.app.save_config_only()

        self._label_var.trace_add("write", _on_change)
        self._h_var.trace_add("write", _on_change)
        self._m_var.trace_add("write", _on_change)
        self._s_var.trace_add("write", _on_change)

    def _tick_progress(self) -> None:
        if not self.winfo_exists():
            return
        try:
            full_w = self.winfo_width()
            if full_w > 1 and self._total > 0 and self._state in ("running", "paused", "done"):
                pct = 1 - (self._remaining / self._total) if self._state != "done" else 1.0
                self._progress.configure(width=max(1, int(pct * full_w)))
            else:
                self._progress.configure(width=1)
        except Exception:
            pass
        self.after(120, self._tick_progress)

    def _set_state(self, st: str) -> None:
        self._state = st
        names = {"idle": "IDLE", "running": "RUNNING", "paused": "PAUSED", "done": "DONE"}
        colors = {
            "idle":    theme.TEXT_4,
            "running": theme.ACCENT,
            "paused":  theme.WARNING,
            "done":    theme.DANGER,
        }
        self._state_label.configure(text=f"· {names[st]}", text_color=colors[st])
        if st == "running":
            self.configure(border_color=theme.ACCENT_BORDER)
            self._display.configure(text_color=theme.ACCENT)
        elif st == "done":
            self.configure(border_color=theme.DANGER_BORDER)
            self._blink_done()
        else:
            self.configure(border_color=theme.BORDER_SOFT)
            self._display.configure(text_color=theme.TEXT_1)

    def _blink_done(self) -> None:
        self._blink_on = True
        def step():
            if not self.winfo_exists() or self._state != "done":
                return
            self._display.configure(text_color=theme.DANGER if self._blink_on else theme.TEXT_3)
            self._blink_on = not self._blink_on
            self.after(500, step)
        step()

    def _total_seconds(self) -> int:
        try:
            h = int(self._h_var.get() or "0")
            m = int(self._m_var.get() or "0")
            s = int(self._s_var.get() or "0")
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
            self._total = float(total)
            self._remaining = float(total)
        elif self._state == "paused":
            pass
        else:
            return

        self._set_state("running")
        self._start_btn.configure(state="disabled")
        self._pause_btn.configure(state="normal")
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def _pause(self) -> None:
        if self._state == "running":
            self._set_state("paused")
            self._stop_event.set()
            self._start_btn.configure(text="Resume", state="normal")
            self._pause_btn.configure(state="disabled")

    def _reset(self) -> None:
        self._set_state("idle")
        self._stop_event.set()
        total = self._total_seconds()
        self._total = float(total) if total > 0 else 1.0
        self._remaining = float(total)
        if self.winfo_exists():
            self._display.configure(text=self._format(total))
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
            if self.winfo_exists():
                self.after(0, self._on_done)

    def _update_display(self) -> None:
        if self.winfo_exists():
            self._display.configure(text=self._format(self._remaining))

    def _on_done(self) -> None:
        self._set_state("done")
        if self.winfo_exists():
            self._display.configure(text="00:00:00")
            self._start_btn.configure(state="disabled")
            self._pause_btn.configure(state="disabled")
        self.tab.notify(self._label_var.get())


class _TimerPopup(ctk.CTkToplevel):
    def __init__(self, parent, label: str) -> None:
        super().__init__(parent, fg_color=theme.BG_SURFACE)
        self.title("Timer Finished")
        self.geometry("360x180")
        self.resizable(False, False)
        self.attributes("-topmost", True)

        ctk.CTkLabel(
            self, text="⏰  Timer Finished",
            font=theme.font(18, "bold"),
            text_color=theme.WARNING, fg_color="transparent",
        ).pack(pady=(28, 8))

        ctk.CTkLabel(
            self, text=label,
            font=theme.font(13), text_color=theme.TEXT_2,
            fg_color="transparent",
        ).pack()

        from ui.widgets import PrimaryButton as _Btn
        _Btn(self, text="OK", command=self.destroy).pack(pady=(20, 0))

        self.after(120, self.grab_set)
        self.lift()
        self.focus_force()
