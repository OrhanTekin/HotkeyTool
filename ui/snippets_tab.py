"""
Snippets tab: manage text abbreviation→expansion pairs.
"""
from __future__ import annotations

import copy
from typing import TYPE_CHECKING

import customtkinter as ctk
from tkinter import messagebox

from ui import theme
from ui.widgets import (
    DangerButton, GhostButton, IconButton, PrimaryButton, Row, Switch,
)

if TYPE_CHECKING:
    from app import App
    from core.models import Snippet


class SnippetsTab(ctk.CTkFrame):
    def __init__(self, parent: ctk.CTkBaseClass, app: "App") -> None:
        super().__init__(parent, fg_color=theme.BG_BASE)
        self.app = app
        self._rows: list[_SnippetRow] = []
        self._build()
        self.refresh()

    def _build(self) -> None:
        tb = ctk.CTkFrame(self, fg_color="transparent", height=58)
        tb.pack(fill="x", padx=18, pady=(14, 8))
        tb.pack_propagate(False)

        PrimaryButton(tb, text="+  Add Snippet", command=self._add).pack(side="left")

        ctk.CTkLabel(
            tb,
            text="Type the abbreviation anywhere — it expands automatically.",
            font=theme.font(11), text_color=theme.TEXT_3, fg_color="transparent",
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
        _ch("Active",       width=58,  side="left")
        _ch("Abbreviation", width=140, side="left", padx=(0, 14))
        _ch("Expansion", anchor="w", side="left", fill="x", expand=True, padx=(0, 8))

        self._scroll = ctk.CTkScrollableFrame(
            self, fg_color=theme.BG_BASE,
            scrollbar_button_color=theme.BG_ELEVATED,
            scrollbar_button_hover_color=theme.BORDER_STRONG,
        )
        self._scroll.pack(fill="both", expand=True, padx=10, pady=(8, 8))

        self._empty = ctk.CTkFrame(self._scroll, fg_color="transparent")
        ctk.CTkLabel(
            self._empty, text="❝",
            font=theme.font(28), text_color=theme.TEXT_3, fg_color=theme.BG_ELEVATED,
            width=56, height=56, corner_radius=14,
        ).pack(pady=(0, 14))
        ctk.CTkLabel(
            self._empty, text="No snippets yet",
            font=theme.font(14, "bold"), text_color=theme.TEXT_1,
        ).pack()
        ctk.CTkLabel(
            self._empty,
            text='Example: "@@email" → your full email address.',
            font=theme.font(12), text_color=theme.TEXT_3, wraplength=320, justify="center",
        ).pack(pady=(4, 0))

    def refresh(self) -> None:
        for row in self._rows:
            row.destroy()
        self._rows.clear()
        self._empty.pack_forget()

        snippets = self.app.config.snippets
        if not snippets:
            self._empty.pack(pady=60)
        else:
            for i, s in enumerate(snippets):
                row = _SnippetRow(self._scroll, self.app, s, i, self)
                row.pack(fill="x", pady=(0, 6), padx=2)
                self._rows.append(row)

    def _add(self) -> None:
        _SnippetEditor(self, self.app, None)


class _SnippetRow(Row):
    def __init__(self, parent, app: "App", snippet: "Snippet", index: int, tab: SnippetsTab):
        super().__init__(parent, dim=not snippet.enabled, height=48)
        self.pack_propagate(False)
        self.app = app
        self.snippet = snippet
        self.tab = tab
        self._build()

    def _build(self) -> None:
        Switch(self, on=self.snippet.enabled, command=self._toggle
               ).pack(side="left", padx=(14, 12), pady=10)

        # Fixed-width container keeps column aligned with col_head "Abbreviation" (140px)
        abbr_col = ctk.CTkFrame(self, fg_color="transparent", width=140, height=48)
        abbr_col.pack(side="left", padx=(0, 14))
        abbr_col.pack_propagate(False)
        ctk.CTkLabel(
            abbr_col, text=self.snippet.abbreviation,
            font=theme.mono(11, "bold"),
            anchor="center",
            fg_color=theme.ACCENT_BG, corner_radius=6,
            text_color=theme.ACCENT,
            padx=10,
        ).place(relx=0.5, rely=0.5, anchor="center")

        # Expansion preview
        preview = self.snippet.expansion.replace("\n", " ")
        if len(preview) > 80:
            preview = preview[:80] + "…"
        ctk.CTkLabel(
            self, text=preview, anchor="w",
            font=theme.font(12),
            text_color=theme.TEXT_2 if self.snippet.enabled else theme.TEXT_3,
            fg_color="transparent",
        ).pack(side="left", padx=(0, 8), fill="x", expand=True, pady=10)

        # Hover-revealed actions
        actions = ctk.CTkFrame(self, fg_color="transparent")
        GhostButton(actions, text="Edit", small=True, command=self._edit
                    ).pack(side="left", padx=2)
        DangerButton(actions, text="Delete", small=True, command=self._delete
                     ).pack(side="left", padx=(2, 12))
        self.set_actions_widget(actions, {"side": "right"})

    def _toggle(self, on: bool) -> None:
        self.snippet.enabled = on
        self.app.save_config_only()
        self.app.snippets.stop()
        self.app.snippets.start()
        if self.app.window:
            self.app.window.toast("Snippet updated")

    def _edit(self) -> None:
        _SnippetEditor(self.tab, self.app, self.snippet)

    def _delete(self) -> None:
        try:
            self.app.config.snippets.remove(self.snippet)
        except ValueError:
            pass
        self.app.save_config_only()
        self.tab.refresh()
        if self.app.window:
            self.app.window.toast("Snippet deleted")


class _SnippetEditor(ctk.CTkToplevel):
    def __init__(self, parent, app: "App", snippet: "Snippet | None"):
        super().__init__(parent)
        self.app = app
        self._original = snippet
        from core.models import Snippet as Sn
        self._working = Sn.new() if snippet is None else copy.deepcopy(snippet)

        self.title("New Snippet" if snippet is None else "Edit Snippet")
        self.geometry("500x300")
        self.resizable(False, False)
        self.attributes("-topmost", True)
        self.configure(fg_color=theme.BG_SURFACE)
        self._build()
        self.after(120, self.grab_set)
        self.after(300, lambda: self.attributes("-topmost", False))
        self.lift()
        self.focus_force()

    def _build(self) -> None:
        pad = {"padx": 20, "pady": (10, 0)}

        r1 = ctk.CTkFrame(self, fg_color="transparent")
        r1.pack(fill="x", **pad)
        ctk.CTkLabel(r1, text="Abbreviation:", width=110, anchor="w",
                     font=theme.font(13), text_color=theme.TEXT_1).pack(side="left")
        self._abbr_var = ctk.StringVar(value=self._working.abbreviation)
        ctk.CTkEntry(r1, textvariable=self._abbr_var, width=300, height=32,
                     fg_color=theme.BG_INPUT, border_color=theme.BORDER, border_width=1,
                     text_color=theme.TEXT_1, font=theme.mono(12),
                     placeholder_text="e.g.  @@email").pack(side="left", padx=4)

        r2 = ctk.CTkFrame(self, fg_color="transparent")
        r2.pack(fill="x", **pad)
        ctk.CTkLabel(r2, text="Expansion:", width=110, anchor="nw",
                     font=theme.font(13), text_color=theme.TEXT_1).pack(side="left", anchor="n")
        self._exp_box = ctk.CTkTextbox(
            r2, width=300, height=100, font=theme.font(12),
            fg_color=theme.BG_INPUT, border_color=theme.BORDER, border_width=1,
            text_color=theme.TEXT_1,
        )
        self._exp_box.pack(side="left", padx=4)
        self._exp_box.insert("1.0", self._working.expansion)

        ctk.CTkLabel(
            self,
            text="Tip: the abbreviation is replaced as you type it in any app.",
            font=theme.font(10), text_color=theme.TEXT_3,
        ).pack(padx=20, pady=(6, 0), anchor="w")

        foot = ctk.CTkFrame(self, fg_color="transparent", height=50)
        foot.pack(fill="x", padx=20, pady=(8, 12), side="bottom")
        foot.pack_propagate(False)
        GhostButton(foot, text="Cancel", command=self.destroy).pack(side="right", padx=(6, 0))
        PrimaryButton(foot, text="Save Snippet", command=self._save).pack(side="right")

    def _save(self) -> None:
        abbr = self._abbr_var.get().strip()
        exp  = self._exp_box.get("1.0", "end-1c")
        if not abbr:
            messagebox.showwarning("Validation", "Please enter an abbreviation.", parent=self)
            return
        if not exp:
            messagebox.showwarning("Validation", "Please enter the expansion text.", parent=self)
            return

        self._working.abbreviation = abbr
        self._working.expansion    = exp

        if self._original is None:
            self.app.config.snippets.append(self._working)
        else:
            idx = next((i for i, s in enumerate(self.app.config.snippets)
                        if s.id == self._original.id), None)
            if idx is not None:
                self.app.config.snippets[idx] = self._working

        self.app.save_config_only()
        self.app.snippets.stop()
        self.app.snippets.start()
        # Refresh parent tab
        parent = self.master
        if hasattr(parent, "refresh"):
            parent.refresh()
        self.destroy()
