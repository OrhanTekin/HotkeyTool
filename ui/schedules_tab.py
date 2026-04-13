"""
Schedules tab: list of time-based binding triggers.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

import customtkinter as ctk

if TYPE_CHECKING:
    from app import App
    from core.models import Schedule

_ROW_EVEN = ("#1a1a2e", "#1a1a2e")
_ROW_ODD  = ("#16162a", "#16162a")
_DAY_NAMES = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


class SchedulesTab(ctk.CTkFrame):
    def __init__(self, parent: ctk.CTkBaseClass, app: "App") -> None:
        super().__init__(parent, fg_color="transparent")
        self.app = app
        self._rows: list[_ScheduleRow] = []
        self._build()
        self.refresh()

    # ── layout ────────────────────────────────────────────────────────────────

    def _build(self) -> None:
        tb = ctk.CTkFrame(self, fg_color="transparent", height=50)
        tb.pack(fill="x", padx=4, pady=(4, 0))
        tb.pack_propagate(False)

        ctk.CTkButton(
            tb, text="+ Add Schedule",
            width=148, height=36,
            font=ctk.CTkFont(size=13, weight="bold"),
            command=self._add,
        ).pack(side="left")

        # Column headers
        hdr = ctk.CTkFrame(self, fg_color=("#0f0f22", "#0f0f22"), height=28, corner_radius=6)
        hdr.pack(fill="x", padx=4, pady=(6, 0))
        hdr.pack_propagate(False)

        for text, width in [
            ("",       44),
            ("Time",   80),
            ("Days",   200),
            ("Binding", 0),
        ]:
            ctk.CTkLabel(
                hdr, text=text, width=width, anchor="w",
                font=ctk.CTkFont(size=11, weight="bold"),
                text_color=("#666688", "#666688"),
            ).pack(side="left", padx=(8 if width == 44 else 4, 0))

        self._scroll = ctk.CTkScrollableFrame(self, fg_color="transparent")
        self._scroll.pack(fill="both", expand=True, padx=4, pady=(4, 4))

        self._empty = ctk.CTkLabel(
            self._scroll,
            text="No schedules yet.\nClick '+ Add Schedule' to create one.",
            font=ctk.CTkFont(size=14),
            text_color=("#444466", "#444466"),
            justify="center",
        )

    # ── public ────────────────────────────────────────────────────────────────

    def refresh(self) -> None:
        for row in self._rows:
            row.destroy()
        self._rows.clear()

        schedules = self.app.config.schedules
        if not schedules:
            self._empty.pack(pady=48)
        else:
            self._empty.pack_forget()
            for i, s in enumerate(schedules):
                row = _ScheduleRow(self._scroll, self.app, s, i, self)
                row.pack(fill="x", pady=(0, 2))
                self._rows.append(row)

    # ── internals ─────────────────────────────────────────────────────────────

    def _add(self) -> None:
        from ui.schedule_editor import ScheduleEditor
        ScheduleEditor(self, self.app, None)


# ── row widget ────────────────────────────────────────────────────────────────

class _ScheduleRow(ctk.CTkFrame):
    def __init__(
        self,
        parent: ctk.CTkBaseClass,
        app: "App",
        schedule: "Schedule",
        index: int,
        tab: SchedulesTab,
    ) -> None:
        bg = _ROW_EVEN if index % 2 == 0 else _ROW_ODD
        super().__init__(parent, fg_color=(bg[0], bg[1]), corner_radius=6, height=44)
        self.pack_propagate(False)
        self.app = app
        self.schedule = schedule
        self.tab = tab
        self._build()

    def _build(self) -> None:
        # Enable switch
        self._sw = ctk.CTkSwitch(self, text="", width=46, height=22)
        if self.schedule.enabled:
            self._sw.select()
        else:
            self._sw.deselect()
        self._sw.configure(command=self._toggle)
        self._sw.pack(side="left", padx=(8, 2))

        # Time chip
        ctk.CTkLabel(
            self, text=self.schedule.time,
            font=ctk.CTkFont(size=12, weight="bold", family="Courier New"),
            width=68, anchor="center",
            fg_color=("#1e3a5c", "#1e3a5c"),
            corner_radius=4,
            text_color=("#88ccff", "#88ccff"),
        ).pack(side="left", padx=4, pady=7)

        # Days
        ctk.CTkLabel(
            self, text=self._days_str(),
            font=ctk.CTkFont(size=11),
            width=192, anchor="w",
            text_color=("#aaaacc", "#aaaacc"),
        ).pack(side="left", padx=4)

        # Buttons
        btn_frm = ctk.CTkFrame(self, fg_color="transparent")
        btn_frm.pack(side="right", padx=6)

        ctk.CTkButton(
            btn_frm, text="Delete", width=62, height=28,
            fg_color=("#5c1a1a", "#5c1a1a"), hover_color=("#7a2222", "#7a2222"),
            font=ctk.CTkFont(size=11),
            command=self._delete,
        ).pack(side="right", padx=(2, 0))

        ctk.CTkButton(
            btn_frm, text="Edit", width=54, height=28,
            fg_color=("#1a3028", "#1a3028"), hover_color=("#243c32", "#243c32"),
            font=ctk.CTkFont(size=11),
            command=self._edit,
        ).pack(side="right", padx=2)

        # Binding name (expands to fill remaining space)
        binding = next(
            (b for b in self.app.config.bindings if b.id == self.schedule.binding_id),
            None,
        )
        name = binding.name if binding else "(binding deleted)"
        color = ("#d8d8ee", "#d8d8ee") if binding else ("#884444", "#884444")

        ctk.CTkLabel(
            self, text=name,
            font=ctk.CTkFont(size=12),
            anchor="w", width=1,
            text_color=color,
        ).pack(side="left", padx=4, fill="x", expand=True)

    def _days_str(self) -> str:
        days = sorted(self.schedule.days)
        if days == list(range(7)):
            return "Every day"
        if days == list(range(5)):
            return "Weekdays (Mon–Fri)"
        if days == [5, 6]:
            return "Weekends (Sat–Sun)"
        return "  ".join(_DAY_NAMES[d] for d in days)

    def _toggle(self) -> None:
        self.schedule.enabled = bool(self._sw.get())
        self.app.save_and_reload_schedules()

    def _edit(self) -> None:
        from ui.schedule_editor import ScheduleEditor
        ScheduleEditor(self.tab, self.app, self.schedule)

    def _delete(self) -> None:
        try:
            self.app.config.schedules.remove(self.schedule)
        except ValueError:
            pass
        self.app.save_and_reload_schedules()
