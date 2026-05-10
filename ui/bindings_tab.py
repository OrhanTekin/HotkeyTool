"""
Bindings tab: scrollable list of hotkey bindings with add/edit/delete/duplicate.
"""
from __future__ import annotations

import os
from typing import TYPE_CHECKING

import customtkinter as ctk

from core.models import Binding
from ui import theme
from ui.icons import icon as ui_icon
from ui.widgets import (
    ActionTag, DangerButton, GhostButton, HotkeyChip, IconButton,
    PrimaryButton, Row, Search, Switch,
)

if TYPE_CHECKING:
    from app import App


class BindingsTab(ctk.CTkFrame):
    def __init__(self, parent: ctk.CTkBaseClass, app: "App") -> None:
        super().__init__(parent, fg_color=theme.BG_BASE)
        self.app = app
        self._rows: list[_BindingRow] = []
        self._query = ""
        self._build()
        self.refresh()

    # ── layout ────────────────────────────────────────────────────────────────

    def _build(self) -> None:
        # Toolbar
        tb = ctk.CTkFrame(
            self, fg_color="transparent", height=58, corner_radius=0,
        )
        tb.pack(fill="x", padx=18, pady=(14, 8))
        tb.pack_propagate(False)

        PrimaryButton(tb, text="+  Add Binding", command=self._add).pack(side="left")

        ctk.CTkLabel(
            tb, text="Bind a hotkey to a sequence of actions.",
            font=theme.font(11), text_color=theme.TEXT_3,
            fg_color="transparent",
        ).pack(side="left", padx=(12, 0))

        self._search = Search(
            tb, placeholder="Search bindings...",
            on_change=self._on_search, width=280, height=32,
        )
        self._search.pack(side="right")

        # Toolbar underline
        ctk.CTkFrame(self, height=1, fg_color=theme.BORDER_SOFT, corner_radius=0
                     ).pack(fill="x")

        # Column header — mirrors the exact spacing of _BindingRow so each label
        # shares the same x coordinate as its corresponding column content.
        col_head = ctk.CTkFrame(self, fg_color="transparent", height=24)
        col_head.pack(fill="x", padx=12, pady=(10, 4))
        col_head.pack_propagate(False)

        def _col_lbl(text, *, width: int | None = None, anchor: str = "center", **pack_kw):
            kw = {"width": width} if width else {}
            ctk.CTkLabel(
                col_head, text=text.upper(),
                font=theme.font(10, "bold"), text_color=theme.TEXT_4,
                anchor=anchor, fg_color="transparent", **kw,
            ).pack(**pack_kw)

        # "Actions" packed on the right first so Name's expand fills the middle.
        _col_lbl("Actions", side="right", padx=(0, 16))
        # 26px spacer aligns "Active" label with the switch's left edge in rows.
        ctk.CTkFrame(col_head, fg_color="transparent", width=26).pack(side="left")
        # "Active" covers the switch knob + its right gap (32 + 12 = 44px).
        _col_lbl("Active", width=44, side="left")
        # "Hotkey" at 180 + 12 padx = 192 total, matching chip_col width in rows.
        _col_lbl("Hotkey", width=180, side="left", padx=(0, 12))
        # "Name" left-aligned to match where the name text starts in each row.
        _col_lbl("Name", anchor="w", side="left", fill="x", expand=True, padx=(0, 8))

        # Scrollable list
        self._scroll = ctk.CTkScrollableFrame(
            self, fg_color=theme.BG_BASE, scrollbar_button_color=theme.BG_ELEVATED,
            scrollbar_button_hover_color=theme.BORDER_STRONG,
        )
        self._scroll.pack(fill="both", expand=True, padx=10, pady=(0, 8))

        # Empty state
        self._empty = ctk.CTkFrame(self._scroll, fg_color="transparent")
        ctk.CTkLabel(
            self._empty, text="⚡",
            font=theme.font(28),
            text_color=theme.TEXT_3, fg_color=theme.BG_ELEVATED,
            width=56, height=56, corner_radius=14,
        ).pack(pady=(0, 14))
        ctk.CTkLabel(
            self._empty, text="No bindings yet",
            font=theme.font(14, "bold"), text_color=theme.TEXT_1,
        ).pack()
        ctk.CTkLabel(
            self._empty, text="Click '+ Add Binding' to bind a hotkey to a sequence of actions.",
            font=theme.font(12), text_color=theme.TEXT_3, wraplength=320, justify="center",
        ).pack(pady=(4, 0))

    # ── public ────────────────────────────────────────────────────────────────

    def refresh(self) -> None:
        for row in self._rows:
            row.destroy()
        self._rows.clear()
        self._empty.pack_forget()

        bindings = self.app.config.bindings
        q = self._query.lower().strip()
        if q:
            bindings = [b for b in bindings if q in b.name.lower() or q in b.hotkey.lower()]

        if not bindings:
            self._empty.pack(pady=60)
        else:
            for i, b in enumerate(bindings):
                row = _BindingRow(self._scroll, self.app, b, i, self)
                row.pack(fill="x", pady=(0, 6), padx=2)
                self._rows.append(row)

    def move_binding(self, binding: Binding, direction: int) -> None:
        lst = self.app.config.bindings
        idx = lst.index(binding)
        new_idx = idx + direction
        if new_idx < 0 or new_idx >= len(lst):
            return
        lst[idx], lst[new_idx] = lst[new_idx], lst[idx]
        self.app.save_and_reload()

    def update_listening_button(self) -> None:
        # listening pill lives in the global header now
        if self.app.window:
            self.app.window.update_listening_state()

    # ── internals ─────────────────────────────────────────────────────────────

    def _on_search(self, q: str) -> None:
        self._query = q
        self.refresh()

    def _add(self) -> None:
        from ui.binding_editor import BindingEditor
        BindingEditor(self, self.app, None)


# ── row widget ────────────────────────────────────────────────────────────────

class _BindingRow(Row):
    def __init__(self, parent, app: "App", binding: Binding, index: int,
                 tab: BindingsTab) -> None:
        super().__init__(parent, dim=not binding.enabled, height=58)
        self.pack_propagate(False)
        self.app = app
        self.binding = binding
        self.tab = tab
        self._build()

    def _build(self) -> None:
        dim = not self.binding.enabled

        # Switch (left)
        sw = Switch(self, on=self.binding.enabled, command=self._toggle)
        sw.pack(side="left", padx=(14, 12), pady=10)

        # Fixed-width chip column: chip auto-sizes to content, transparent wrapper
        # keeps the column exactly 192px (≤180px chip + 12px right gap) for
        # alignment with the col header.
        chip_col = ctk.CTkFrame(self, fg_color="transparent", width=192, height=58)
        chip_col.pack_propagate(False)
        chip_col.pack(side="left")
        chip = HotkeyChip(chip_col, self.binding.hotkey, dim=dim)
        chip.place(relx=0.5, rely=0.5, anchor="center")

        # Center column: name only (no action tags)
        center = ctk.CTkFrame(self, fg_color="transparent")
        center.pack(side="left", fill="both", expand=True, padx=(0, 8))
        ctk.CTkLabel(
            center, text=self.binding.name or "(unnamed)",
            font=theme.font(13, "bold" if not dim else "normal"),
            text_color=theme.TEXT_3 if dim else theme.TEXT_1,
            fg_color="transparent", anchor="w",
        ).pack(fill="both", expand=True)

        # Right: hover-revealed icon buttons matching the design.
        actions = ctk.CTkFrame(self, fg_color="transparent")
        IconButton(actions, image=ui_icon("chevU", 12, theme.TEXT_2),
                   command=lambda: self.tab.move_binding(self.binding, -1),
                   kind="ghost", size=26).pack(side="left", padx=2)
        IconButton(actions, image=ui_icon("chevD", 12, theme.TEXT_2),
                   command=lambda: self.tab.move_binding(self.binding, 1),
                   kind="ghost", size=26).pack(side="left", padx=2)
        IconButton(actions, image=ui_icon("edit", 12, theme.TEXT_2),
                   command=self._edit, kind="ghost", size=26
                   ).pack(side="left", padx=2)
        IconButton(actions, image=ui_icon("dupe", 12, theme.TEXT_2),
                   command=self._duplicate, kind="ghost", size=26
                   ).pack(side="left", padx=2)
        IconButton(actions, image=ui_icon("trash", 12, theme.DANGER),
                   command=self._delete, kind="danger", size=26
                   ).pack(side="left", padx=(2, 12))
        self.set_actions_widget(actions, {"side": "right"})

    # ── callbacks ─────────────────────────────────────────────────────────────

    def _toggle(self, on: bool) -> None:
        self.binding.enabled = on
        self.app.save_and_reload()
        if self.app.window:
            self.app.window.toast("Binding updated")

    def _edit(self) -> None:
        from ui.binding_editor import BindingEditor
        BindingEditor(self.tab, self.app, self.binding)

    def _duplicate(self) -> None:
        self.app.config.bindings.append(self.binding.duplicate())
        self.app.save_and_reload()
        if self.app.window:
            self.app.window.toast("Binding duplicated")

    def _delete(self) -> None:
        try:
            self.app.config.bindings.remove(self.binding)
        except ValueError:
            pass
        self.app.save_and_reload()
        if self.app.window:
            self.app.window.toast("Binding deleted")


# ── helpers ─────────────────────────────────────────────────────────────────────

def _kind_label(action_type: str) -> str:
    return {
        "open_url":       "URL",
        "open_app":       "App",
        "type_text":      "Text",
        "run_command":    "Cmd",
        "send_keys":      "Keys",
        "media_control":  "Media",
        "toggle_topmost": "Top",
        "replay_macro":   "Macro",
    }.get(action_type, action_type)


def _short_value(action) -> str:
    if not action.value:
        return ""
    if action.type == "open_app":
        return os.path.basename(action.value)[:18]
    return action.value[:24]
