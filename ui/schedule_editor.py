"""
Modal dialog for creating or editing a Schedule.
"""
from __future__ import annotations

import copy
import re
from typing import TYPE_CHECKING, List

import customtkinter as ctk
from tkinter import messagebox

from core.models import Schedule
from ui import theme
from ui.widgets import GhostButton, PrimaryButton

if TYPE_CHECKING:
    from app import App

_DAY_LABELS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


class ScheduleEditor(ctk.CTkToplevel):
    def __init__(
        self,
        parent: ctk.CTkBaseClass,
        app: "App",
        schedule: Schedule | None,
    ) -> None:
        super().__init__(parent)
        self.app = app
        self._original = schedule
        self._working = Schedule.new() if schedule is None else copy.deepcopy(schedule)

        self.title("New Schedule" if schedule is None else "Edit Schedule")
        self.geometry("580x390")
        self.resizable(False, False)
        self.attributes("-topmost", True)
        self.configure(fg_color=theme.BG_SURFACE)

        self._build()
        self.after(120, self.grab_set)
        self.after(300, lambda: self.attributes("-topmost", False))
        from utils.resource_path import apply_window_icon
        self.after(200, lambda: apply_window_icon(self))
        self.lift()
        self.focus_force()

    # ── layout ────────────────────────────────────────────────────────────────

    def _build(self) -> None:
        pad = {"padx": 20, "pady": (10, 0)}
        _entry_kw = dict(fg_color=theme.BG_INPUT, border_color=theme.BORDER,
                         border_width=1, text_color=theme.TEXT_1)

        # Name
        r = ctk.CTkFrame(self, fg_color="transparent")
        r.pack(fill="x", **pad)
        ctk.CTkLabel(r, text="Name:", width=82, anchor="w",
                     font=theme.font(13), text_color=theme.TEXT_1).pack(side="left")
        self.name_var = ctk.StringVar(value=self._working.name)
        ctk.CTkEntry(r, textvariable=self.name_var, width=320, height=32,
                     font=theme.font(12), placeholder_text="e.g. Morning startup",
                     **_entry_kw).pack(side="left", padx=4)

        # Binding selector
        r2 = ctk.CTkFrame(self, fg_color="transparent")
        r2.pack(fill="x", **pad)
        ctk.CTkLabel(r2, text="Binding:", width=82, anchor="w",
                     font=theme.font(13), text_color=theme.TEXT_1).pack(side="left")

        bindings = self.app.config.bindings
        names = [b.name for b in bindings] if bindings else ["(no bindings)"]
        cur = next((b.name for b in bindings if b.id == self._working.binding_id), names[0])
        self._binding_var = ctk.StringVar(value=cur)
        ctk.CTkOptionMenu(
            r2, variable=self._binding_var,
            values=names, width=320, height=32,
            fg_color=theme.BG_ELEVATED, button_color=theme.BG_HOVER,
            button_hover_color=theme.BORDER_STRONG, text_color=theme.TEXT_1,
            font=theme.font(12),
        ).pack(side="left", padx=4)

        # Time
        r3 = ctk.CTkFrame(self, fg_color="transparent")
        r3.pack(fill="x", **pad)
        ctk.CTkLabel(r3, text="Time:", width=82, anchor="w",
                     font=theme.font(13), text_color=theme.TEXT_1).pack(side="left")
        self.time_var = ctk.StringVar(value=self._working.time)
        ctk.CTkEntry(
            r3, textvariable=self.time_var,
            width=90, height=32,
            font=theme.mono(12), placeholder_text="09:00",
            **_entry_kw,
        ).pack(side="left", padx=4)
        ctk.CTkLabel(
            r3, text="24-hour format  (e.g. 09:00 / 21:30)",
            font=theme.font(10), text_color=theme.TEXT_3,
        ).pack(side="left")

        # Days
        rf = ctk.CTkFrame(self, fg_color="transparent")
        rf.pack(fill="x", **pad)
        ctk.CTkLabel(rf, text="Days:", width=82, anchor="w",
                     font=theme.font(13), text_color=theme.TEXT_1).pack(side="left")

        self._day_vars: List[ctk.BooleanVar] = []
        for i, name in enumerate(_DAY_LABELS):
            var = ctk.BooleanVar(value=(i in self._working.days))
            self._day_vars.append(var)
            ctk.CTkCheckBox(
                rf, text=name, variable=var,
                width=46, height=22, font=theme.font(11),
                text_color=theme.TEXT_2, fg_color=theme.ACCENT,
                hover_color=theme.ACCENT_MID,
                checkbox_width=16, checkbox_height=16,
            ).pack(side="left", padx=1)

        # Quick-select presets
        qf = ctk.CTkFrame(self, fg_color="transparent")
        qf.pack(fill="x", padx=20, pady=(4, 0))
        ctk.CTkLabel(qf, text="", width=82).pack(side="left")
        for label, days in [
            ("Every day", list(range(7))),
            ("Weekdays",  list(range(5))),
            ("Weekend",   [5, 6]),
        ]:
            GhostButton(qf, text=label, small=True,
                        command=lambda d=days: self._set_days(d)).pack(side="left", padx=2)

        # Enabled
        r4 = ctk.CTkFrame(self, fg_color="transparent")
        r4.pack(fill="x", **pad)
        ctk.CTkLabel(r4, text="Enabled:", width=82, anchor="w",
                     font=theme.font(13), text_color=theme.TEXT_1).pack(side="left")
        self._enabled_sw = ctk.CTkSwitch(
            r4, text="", width=46, height=22,
            fg_color=theme.BG_ELEVATED, progress_color=theme.SUCCESS,
            button_color=theme.TEXT_2, button_hover_color=theme.TEXT_1,
        )
        if self._working.enabled:
            self._enabled_sw.select()
        else:
            self._enabled_sw.deselect()
        self._enabled_sw.pack(side="left", padx=4)

        # Footer
        foot = ctk.CTkFrame(self, fg_color="transparent", height=54)
        foot.pack(fill="x", padx=20, pady=(16, 14), side="bottom")
        foot.pack_propagate(False)

        GhostButton(foot, text="Cancel", command=self.destroy).pack(side="right", padx=(6, 0))
        PrimaryButton(foot, text="Save Schedule", command=self._save).pack(side="right")

    # ── helpers ───────────────────────────────────────────────────────────────

    def _set_days(self, days: List[int]) -> None:
        for i, var in enumerate(self._day_vars):
            var.set(i in days)

    # ── save ─────────────────────────────────────────────────────────────────

    def _save(self) -> None:
        name     = self.name_var.get().strip()
        time_str = self.time_var.get().strip()

        if not name:
            messagebox.showwarning("Validation", "Please enter a name.", parent=self)
            return

        if not re.match(r"^\d{2}:\d{2}$", time_str):
            messagebox.showwarning("Validation",
                                   "Time must be in HH:MM format (e.g. 09:00).", parent=self)
            return
        h, m = map(int, time_str.split(":"))
        if not (0 <= h < 24 and 0 <= m < 60):
            messagebox.showwarning("Validation",
                                   "Invalid time. Hours 0–23, minutes 0–59.", parent=self)
            return

        days = [i for i, v in enumerate(self._day_vars) if v.get()]
        if not days:
            messagebox.showwarning("Validation",
                                   "Please select at least one day.", parent=self)
            return

        bindings = self.app.config.bindings
        binding = next(
            (b for b in bindings if b.name == self._binding_var.get()), None
        )
        if not binding:
            messagebox.showwarning("Validation",
                                   "Please select a valid binding.", parent=self)
            return

        self._working.name       = name
        self._working.time       = time_str
        self._working.days       = days
        self._working.binding_id = binding.id
        self._working.enabled    = bool(self._enabled_sw.get())

        if self._original is None:
            self.app.config.schedules.append(self._working)
        else:
            idx = next(
                (i for i, s in enumerate(self.app.config.schedules)
                 if s.id == self._original.id),
                None,
            )
            if idx is not None:
                self.app.config.schedules[idx] = self._working

        self.app.save_and_reload_schedules()
        self.destroy()
