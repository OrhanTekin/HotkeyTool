"""
Bindings tab: scrollable list of hotkey bindings with add/edit/delete/duplicate.
"""
from __future__ import annotations

import os
from typing import TYPE_CHECKING

import customtkinter as ctk

from core.models import Binding

if TYPE_CHECKING:
    from app import App

# ── colour constants ──────────────────────────────────────────────────────────
_ROW_EVEN  = ("#1a1a2e", "#1a1a2e")
_ROW_ODD   = ("#16162a", "#16162a")
_CHIP_BG   = ("#1e3a5c", "#1e3a5c")
_CHIP_DIM  = ("#252535", "#252535")


class BindingsTab(ctk.CTkFrame):
    def __init__(self, parent: ctk.CTkBaseClass, app: "App") -> None:
        super().__init__(parent, fg_color="transparent")
        self.app = app
        self._rows: list[_BindingRow] = []
        self._build()
        self.refresh()

    # ── layout ────────────────────────────────────────────────────────────────

    def _build(self) -> None:
        # Toolbar
        tb = ctk.CTkFrame(self, fg_color="transparent", height=50)
        tb.pack(fill="x", padx=4, pady=(4, 0))
        tb.pack_propagate(False)

        ctk.CTkButton(
            tb, text="+ Add Binding",
            width=148, height=36,
            font=ctk.CTkFont(size=13, weight="bold"),
            command=self._add,
        ).pack(side="left", padx=(0, 8))

        self._listen_btn = ctk.CTkButton(
            tb, text="", width=172, height=36,
            font=ctk.CTkFont(size=13),
            command=self.app.toggle_listening,
        )
        self._listen_btn.pack(side="left")
        self._refresh_listen_btn()

        # Column headers
        hdr = ctk.CTkFrame(self, fg_color=("#0f0f22", "#0f0f22"), height=28, corner_radius=6)
        hdr.pack(fill="x", padx=4, pady=(6, 0))
        hdr.pack_propagate(False)

        for text, width in [
            ("",        44),
            ("Hotkey",  118),
            ("Name",    172),
            ("Actions", 0),     # expands
        ]:
            ctk.CTkLabel(
                hdr, text=text, width=width, anchor="w",
                font=ctk.CTkFont(size=11, weight="bold"),
                text_color=("#666688", "#666688"),
            ).pack(side="left", padx=(8 if width == 44 else 4, 0))

        # Scrollable list
        self._scroll = ctk.CTkScrollableFrame(
            self, fg_color="transparent",
        )
        self._scroll.pack(fill="both", expand=True, padx=4, pady=(4, 4))

        # Empty-state placeholder (shown only when list is empty)
        self._empty = ctk.CTkLabel(
            self._scroll,
            text="No bindings yet.\nClick '+ Add Binding' to get started.",
            font=ctk.CTkFont(size=14),
            text_color=("#444466", "#444466"),
            justify="center",
        )

    # ── public ────────────────────────────────────────────────────────────────

    def refresh(self) -> None:
        for row in self._rows:
            row.destroy()
        self._rows.clear()

        bindings = self.app.config.bindings
        if not bindings:
            self._empty.pack(pady=48)
        else:
            self._empty.pack_forget()
            for i, b in enumerate(bindings):
                row = _BindingRow(self._scroll, self.app, b, i, self)
                row.pack(fill="x", pady=(0, 2))
                self._rows.append(row)

    def update_listening_button(self) -> None:
        self._refresh_listen_btn()

    # ── internals ─────────────────────────────────────────────────────────────

    def _refresh_listen_btn(self) -> None:
        if self.app.listener.is_running():
            self._listen_btn.configure(
                text="\u25cf  Listening  ON",
                fg_color=("#163a22", "#163a22"),
                hover_color=("#1e4a2a", "#1e4a2a"),
                text_color=("#55dd88", "#55dd88"),
            )
        else:
            self._listen_btn.configure(
                text="\u25cb  Listening  OFF",
                fg_color=("#3a1616", "#3a1616"),
                hover_color=("#4a1e1e", "#4a1e1e"),
                text_color=("#dd5555", "#dd5555"),
            )

    def _add(self) -> None:
        from ui.binding_editor import BindingEditor
        BindingEditor(self, self.app, None)


# ── row widget ────────────────────────────────────────────────────────────────

class _BindingRow(ctk.CTkFrame):
    def __init__(
        self,
        parent: ctk.CTkBaseClass,
        app: "App",
        binding: Binding,
        index: int,
        tab: BindingsTab,
    ) -> None:
        bg = _ROW_EVEN if index % 2 == 0 else _ROW_ODD
        super().__init__(parent, fg_color=(bg[0], bg[1]), corner_radius=6, height=44)
        self.pack_propagate(False)
        self.app = app
        self.binding = binding
        self.tab = tab
        self._build()

    def _build(self) -> None:
        dim = not self.binding.enabled

        # Enable switch
        self._sw = ctk.CTkSwitch(self, text="", width=46, height=22)
        if self.binding.enabled:
            self._sw.select()
        else:
            self._sw.deselect()
        self._sw.configure(command=self._toggle)
        self._sw.pack(side="left", padx=(8, 2))

        # Hotkey chip
        hotkey_text = self.binding.hotkey.upper() if self.binding.hotkey else "\u2014"
        chip_bg  = _CHIP_DIM if dim else _CHIP_BG
        chip_fg  = ("#555577", "#555577") if dim else ("#88ccff", "#88ccff")
        ctk.CTkLabel(
            self, text=hotkey_text,
            font=ctk.CTkFont(size=11, weight="bold", family="Courier New"),
            width=112, anchor="center",
            fg_color=(chip_bg[0], chip_bg[1]),
            corner_radius=4,
            text_color=(chip_fg[0], chip_fg[1]),
        ).pack(side="left", padx=4, pady=7)

        # Name
        name_col = ("#555577", "#555577") if dim else ("#d8d8ee", "#d8d8ee")
        ctk.CTkLabel(
            self, text=self.binding.name,
            font=ctk.CTkFont(size=13),
            width=168, anchor="w",
            text_color=(name_col[0], name_col[1]),
        ).pack(side="left", padx=4)

        # Buttons — packed BEFORE summary so they always get their space
        btn_frm = ctk.CTkFrame(self, fg_color="transparent")
        btn_frm.pack(side="right", padx=6)

        ctk.CTkButton(
            btn_frm, text="Delete", width=62, height=28,
            fg_color=("#5c1a1a", "#5c1a1a"), hover_color=("#7a2222", "#7a2222"),
            font=ctk.CTkFont(size=11),
            command=self._delete,
        ).pack(side="right", padx=(2, 0))

        ctk.CTkButton(
            btn_frm, text="Dupe", width=54, height=28,
            fg_color=("#1e2a3a", "#1e2a3a"), hover_color=("#2a3a4a", "#2a3a4a"),
            font=ctk.CTkFont(size=11),
            command=self._duplicate,
        ).pack(side="right", padx=2)

        ctk.CTkButton(
            btn_frm, text="Edit", width=54, height=28,
            fg_color=("#1a3028", "#1a3028"), hover_color=("#243c32", "#243c32"),
            font=ctk.CTkFont(size=11),
            command=self._edit,
        ).pack(side="right", padx=2)

        # Actions summary — fills remaining space, truncated to prevent overflow
        ctk.CTkLabel(
            self, text=self._summary(),
            font=ctk.CTkFont(size=11),
            anchor="w",
            width=1,          # allow shrinking; expand does the stretching
            text_color=("#777799", "#777799"),
        ).pack(side="left", padx=4, fill="x", expand=True)

    def _summary(self) -> str:
        if not self.binding.actions:
            return "No actions"
        _icons = {
            "open_url":       "URL",
            "open_app":       "App",
            "type_text":      "Text",
            "run_command":    "Cmd",
            "send_keys":      "Keys",
            "media_control":  "Media",
            "system_action":  "Sys",
            "toggle_topmost": "Top",
            "replay_macro":   "Macro",
        }
        parts = []
        for a in self.binding.actions[:3]:
            tag = _icons.get(a.type, a.type)
            val = a.value[:18] if a.value else ""
            if a.type == "open_app":
                val = os.path.basename(a.value)[:18]
            parts.append(f"{tag}: {val}" if val else tag)
        extra = len(self.binding.actions) - 3
        if extra > 0:
            parts.append(f"+{extra}")
        text = "  \u2192  ".join(parts)
        # Hard cap so very long values never push the buttons
        return text[:72] + "\u2026" if len(text) > 72 else text

    # ── callbacks ─────────────────────────────────────────────────────────────

    def _toggle(self) -> None:
        self.binding.enabled = bool(self._sw.get())
        self.app.save_and_reload()

    def _edit(self) -> None:
        from ui.binding_editor import BindingEditor
        BindingEditor(self.tab, self.app, self.binding)

    def _duplicate(self) -> None:
        self.app.config.bindings.append(self.binding.duplicate())
        self.app.save_and_reload()

    def _delete(self) -> None:
        try:
            self.app.config.bindings.remove(self.binding)
        except ValueError:
            pass
        self.app.save_and_reload()
