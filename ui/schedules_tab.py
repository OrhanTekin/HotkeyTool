"""
Schedules tab: list of time-based binding triggers.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

import customtkinter as ctk

from ui import theme
from ui.widgets import (
    DangerButton, GhostButton, IconButton, PrimaryButton, Row, Switch,
)

if TYPE_CHECKING:
    from app import App
    from core.models import Schedule

_DAY_LETTERS = ["M", "T", "W", "T", "F", "S", "S"]


class SchedulesTab(ctk.CTkFrame):
    def __init__(self, parent: ctk.CTkBaseClass, app: "App") -> None:
        super().__init__(parent, fg_color=theme.BG_BASE)
        self.app = app
        self._rows: list[_ScheduleRow] = []
        self._build()
        self.refresh()

    # ── layout ────────────────────────────────────────────────────────────────

    def _build(self) -> None:
        tb = ctk.CTkFrame(self, fg_color="transparent", height=58)
        tb.pack(fill="x", padx=18, pady=(14, 8))
        tb.pack_propagate(False)

        PrimaryButton(tb, text="+  Add Schedule", command=self._add).pack(side="left")

        ctk.CTkLabel(
            tb, text="Trigger any binding on a recurring time.",
            font=theme.font(11), text_color=theme.TEXT_3,
            fg_color="transparent",
        ).pack(side="left", padx=(12, 0))

        ctk.CTkFrame(self, height=1, fg_color=theme.BORDER_SOFT, corner_radius=0
                     ).pack(fill="x")

        # Column header
        col_head = ctk.CTkFrame(self, fg_color="transparent", height=24)
        col_head.pack(fill="x", padx=12, pady=(8, 2))
        col_head.pack_propagate(False)

        def _ch(text, *, width=None, anchor="center", **pk):
            kw = {"width": width} if width else {}
            ctk.CTkLabel(col_head, text=text.upper(),
                         font=theme.font(10, "bold"), text_color=theme.TEXT_4,
                         anchor=anchor, fg_color="transparent", **kw).pack(**pk)

        _ch("Actions", side="right", padx=(0, 12))
        _ch("Active", width=58,  side="left")
        _ch("Time",   width=70,  side="left", padx=(0, 12))
        _ch("Days",   width=168, side="left", padx=(0, 12))
        _ch("Binding", anchor="w", side="left", fill="x", expand=True, padx=(0, 8))

        self._scroll = ctk.CTkScrollableFrame(
            self, fg_color=theme.BG_BASE,
            scrollbar_button_color=theme.BG_ELEVATED,
            scrollbar_button_hover_color=theme.BORDER_STRONG,
        )
        self._scroll.pack(fill="both", expand=True, padx=10, pady=(8, 8))

        self._empty = ctk.CTkFrame(self._scroll, fg_color="transparent")
        ctk.CTkLabel(
            self._empty, text="📅",
            font=theme.font(28), text_color=theme.TEXT_3, fg_color=theme.BG_ELEVATED,
            width=56, height=56, corner_radius=14,
        ).pack(pady=(0, 14))
        ctk.CTkLabel(
            self._empty, text="No schedules yet",
            font=theme.font(14, "bold"), text_color=theme.TEXT_1,
        ).pack()
        ctk.CTkLabel(
            self._empty, text="Click '+ Add Schedule' to fire a binding on a recurring time.",
            font=theme.font(12), text_color=theme.TEXT_3, wraplength=320, justify="center",
        ).pack(pady=(4, 0))

    # ── public ────────────────────────────────────────────────────────────────

    def refresh(self) -> None:
        for row in self._rows:
            row.destroy()
        self._rows.clear()
        self._empty.pack_forget()

        schedules = self.app.config.schedules
        if not schedules:
            self._empty.pack(pady=60)
        else:
            for i, s in enumerate(schedules):
                row = _ScheduleRow(self._scroll, self.app, s, i, self)
                row.pack(fill="x", pady=(0, 6), padx=2)
                self._rows.append(row)

    # ── internals ─────────────────────────────────────────────────────────────

    def _add(self) -> None:
        from ui.schedule_editor import ScheduleEditor
        ScheduleEditor(self, self.app, None)


# ── row widget ────────────────────────────────────────────────────────────────

class _ScheduleRow(Row):
    def __init__(self, parent, app: "App", schedule: "Schedule",
                 index: int, tab: SchedulesTab) -> None:
        super().__init__(parent, dim=not schedule.enabled, height=54)
        self.pack_propagate(False)
        self.app = app
        self.schedule = schedule
        self.tab = tab
        self._build()

    def _build(self) -> None:
        dim = not self.schedule.enabled

        # Switch
        sw = Switch(self, on=self.schedule.enabled, command=self._toggle)
        sw.pack(side="left", padx=(14, 12), pady=10)

        # Time chip (mono)
        ctk.CTkLabel(
            self, text=self.schedule.time,
            font=theme.mono(13, "bold"),
            width=58, anchor="center",
            fg_color=theme.ACCENT_BG, corner_radius=6,
            text_color=theme.TEXT_3 if dim else theme.ACCENT,
        ).pack(side="left", padx=(0, 12), pady=10)

        # Day pills
        days_frame = ctk.CTkFrame(self, fg_color="transparent")
        days_frame.pack(side="left", padx=(0, 12), pady=10)
        for di, letter in enumerate(_DAY_LETTERS):
            on = di in self.schedule.days
            ctk.CTkLabel(
                days_frame, text=letter,
                width=22, height=22,
                font=theme.font(10, "bold"),
                fg_color=theme.ACCENT_BG_2 if on else theme.BG_ELEVATED,
                text_color=theme.ACCENT if on else theme.TEXT_4,
                corner_radius=5,
            ).pack(side="left", padx=1)

        # Binding name
        binding = next(
            (b for b in self.app.config.bindings if b.id == self.schedule.binding_id),
            None,
        )
        name_color = theme.TEXT_3 if dim else theme.TEXT_1
        if not binding:
            name_color = theme.DANGER
            name = "(binding deleted)"
        else:
            name = binding.name

        center = ctk.CTkFrame(self, fg_color="transparent")
        center.pack(side="left", fill="both", expand=True, padx=(0, 8))
        ctk.CTkLabel(
            center, text=name,
            font=theme.font(12, "bold"),
            anchor="w", text_color=name_color,
            fg_color="transparent",
        ).pack(anchor="w", pady=(8, 0))
        ctk.CTkLabel(
            center, text=f"→ next at {self._next_str()}" if binding else "(orphan)",
            font=theme.font(11),
            anchor="w", text_color=theme.TEXT_3,
            fg_color="transparent",
        ).pack(anchor="w", pady=(0, 8))

        # Hover-revealed actions
        actions = ctk.CTkFrame(self, fg_color="transparent")
        GhostButton(actions, text="Edit", small=True, command=self._edit
                    ).pack(side="left", padx=2)
        DangerButton(actions, text="Delete", small=True, command=self._delete
                     ).pack(side="left", padx=(2, 12))
        self.set_actions_widget(actions, {"side": "right"})

    def _next_str(self) -> str:
        from datetime import datetime, timedelta
        try:
            now = datetime.now()
            hh, mm = self.schedule.time.split(":")
            target_today = now.replace(hour=int(hh), minute=int(mm), second=0, microsecond=0)
            for offset in range(8):
                check = target_today + timedelta(days=offset)
                if offset == 0 and check < now:
                    continue
                if check.weekday() in self.schedule.days:
                    if check.date() == now.date():
                        return f"Today {self.schedule.time}"
                    return check.strftime(f"%a {self.schedule.time}")
        except Exception:
            pass
        return self.schedule.time

    def _toggle(self, on: bool) -> None:
        self.schedule.enabled = on
        self.app.save_and_reload_schedules()
        if self.app.window:
            self.app.window.toast("Schedule updated")

    def _edit(self) -> None:
        from ui.schedule_editor import ScheduleEditor
        ScheduleEditor(self.tab, self.app, self.schedule)

    def _delete(self) -> None:
        try:
            self.app.config.schedules.remove(self.schedule)
        except ValueError:
            pass
        self.app.save_and_reload_schedules()
        if self.app.window:
            self.app.window.toast("Schedule deleted")
