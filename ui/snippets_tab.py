"""
Snippets tab: manage text abbreviation→expansion pairs.
"""
from __future__ import annotations

import copy
from typing import TYPE_CHECKING

import customtkinter as ctk
from tkinter import messagebox

if TYPE_CHECKING:
    from app import App
    from core.models import Snippet

_ROW_EVEN = ("#1a1a2e", "#1a1a2e")
_ROW_ODD  = ("#16162a", "#16162a")


class SnippetsTab(ctk.CTkFrame):
    def __init__(self, parent: ctk.CTkBaseClass, app: "App") -> None:
        super().__init__(parent, fg_color="transparent")
        self.app = app
        self._rows: list[_SnippetRow] = []
        self._build()
        self.refresh()

    def _build(self) -> None:
        tb = ctk.CTkFrame(self, fg_color="transparent", height=50)
        tb.pack(fill="x", padx=4, pady=(4, 0))
        tb.pack_propagate(False)

        ctk.CTkButton(
            tb, text="+ Add Snippet",
            width=140, height=36,
            font=ctk.CTkFont(size=13, weight="bold"),
            command=self._add,
        ).pack(side="left", padx=(0, 8))

        ctk.CTkLabel(
            tb,
            text="Type an abbreviation anywhere — it expands automatically",
            font=ctk.CTkFont(size=11),
            text_color=("#555577", "#555577"),
        ).pack(side="left", padx=4)

        # Column headers
        hdr = ctk.CTkFrame(self, fg_color=("#0f0f22", "#0f0f22"), height=28, corner_radius=6)
        hdr.pack(fill="x", padx=4, pady=(6, 0))
        hdr.pack_propagate(False)
        for text, width in [("", 44), ("Abbreviation", 150), ("Expansion", 0)]:
            ctk.CTkLabel(
                hdr, text=text, width=width, anchor="w",
                font=ctk.CTkFont(size=11, weight="bold"),
                text_color=("#666688", "#666688"),
            ).pack(side="left", padx=(8 if width == 44 else 4, 0))

        self._scroll = ctk.CTkScrollableFrame(self, fg_color="transparent")
        self._scroll.pack(fill="both", expand=True, padx=4, pady=(4, 4))

        self._empty = ctk.CTkLabel(
            self._scroll,
            text='No snippets yet.\nClick "+ Add Snippet" to create one.\nExample: "@@email" → your full email address.',
            font=ctk.CTkFont(size=13),
            text_color=("#444466", "#444466"),
            justify="center",
        )

    def refresh(self) -> None:
        for row in self._rows:
            row.destroy()
        self._rows.clear()

        snippets = self.app.config.snippets
        if not snippets:
            self._empty.pack(pady=48)
        else:
            self._empty.pack_forget()
            for i, s in enumerate(snippets):
                row = _SnippetRow(self._scroll, self.app, s, i, self)
                row.pack(fill="x", pady=(0, 2))
                self._rows.append(row)

    def _add(self) -> None:
        _SnippetEditor(self, self.app, None)


class _SnippetRow(ctk.CTkFrame):
    def __init__(self, parent, app: "App", snippet: "Snippet", index: int, tab: SnippetsTab):
        bg = _ROW_EVEN if index % 2 == 0 else _ROW_ODD
        super().__init__(parent, fg_color=bg, corner_radius=6, height=44)
        self.pack_propagate(False)
        self.app = app
        self.snippet = snippet
        self.tab = tab
        self._build()

    def _build(self) -> None:
        self._sw = ctk.CTkSwitch(self, text="", width=46, height=22)
        if self.snippet.enabled:
            self._sw.select()
        else:
            self._sw.deselect()
        self._sw.configure(command=self._toggle)
        self._sw.pack(side="left", padx=(8, 2))

        # Abbreviation chip
        ctk.CTkLabel(
            self, text=self.snippet.abbreviation,
            font=ctk.CTkFont(size=12, weight="bold", family="Courier New"),
            width=140, anchor="center",
            fg_color=("#1e3a5c", "#1e3a5c"), corner_radius=4,
            text_color=("#88ccff", "#88ccff"),
        ).pack(side="left", padx=4, pady=7)

        # Buttons
        btn = ctk.CTkFrame(self, fg_color="transparent")
        btn.pack(side="right", padx=6)
        ctk.CTkButton(btn, text="Delete", width=62, height=28,
                      fg_color=("#5c1a1a","#5c1a1a"), hover_color=("#7a2222","#7a2222"),
                      font=ctk.CTkFont(size=11), command=self._delete,
                      ).pack(side="right", padx=(2, 0))
        ctk.CTkButton(btn, text="Edit", width=54, height=28,
                      fg_color=("#1a3028","#1a3028"), hover_color=("#243c32","#243c32"),
                      font=ctk.CTkFont(size=11), command=self._edit,
                      ).pack(side="right", padx=2)

        # Expansion preview
        preview = self.snippet.expansion.replace("\n", " ")[:60]
        ctk.CTkLabel(
            self, text=preview, anchor="w", width=1,
            font=ctk.CTkFont(size=11),
            text_color=("#777799", "#777799"),
        ).pack(side="left", padx=4, fill="x", expand=True)

    def _toggle(self) -> None:
        self.snippet.enabled = bool(self._sw.get())
        self.app.save_config_only()
        self.app.snippets.stop()
        self.app.snippets.start()

    def _edit(self) -> None:
        _SnippetEditor(self.tab, self.app, self.snippet)

    def _delete(self) -> None:
        try:
            self.app.config.snippets.remove(self.snippet)
        except ValueError:
            pass
        self.app.save_config_only()
        self.tab.refresh()


class _SnippetEditor(ctk.CTkToplevel):
    def __init__(self, parent, app: "App", snippet: "Snippet | None"):
        super().__init__(parent)
        self.app = app
        self._original = snippet
        from core.models import Snippet as Sn
        self._working = Sn.new() if snippet is None else copy.deepcopy(snippet)

        self.title("New Snippet" if snippet is None else "Edit Snippet")
        self.geometry("500x280")
        self.resizable(False, False)
        self.attributes("-topmost", True)
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
                     font=ctk.CTkFont(size=13)).pack(side="left")
        self._abbr_var = ctk.StringVar(value=self._working.abbreviation)
        ctk.CTkEntry(r1, textvariable=self._abbr_var, width=300, height=30,
                     font=ctk.CTkFont(size=13, family="Courier New"),
                     placeholder_text="e.g.  @@email").pack(side="left", padx=4)

        r2 = ctk.CTkFrame(self, fg_color="transparent")
        r2.pack(fill="x", **pad)
        ctk.CTkLabel(r2, text="Expansion:", width=110, anchor="nw",
                     font=ctk.CTkFont(size=13)).pack(side="left", anchor="n")
        self._exp_box = ctk.CTkTextbox(r2, width=300, height=100,
                                       font=ctk.CTkFont(size=12))
        self._exp_box.pack(side="left", padx=4)
        self._exp_box.insert("1.0", self._working.expansion)

        ctk.CTkLabel(
            self,
            text="Tip: the abbreviation is replaced as you type it in any app.",
            font=ctk.CTkFont(size=10), text_color=("#555577", "#555577"),
        ).pack(padx=20, pady=(6, 0), anchor="w")

        foot = ctk.CTkFrame(self, fg_color="transparent", height=50)
        foot.pack(fill="x", padx=20, pady=(8, 12), side="bottom")
        foot.pack_propagate(False)
        ctk.CTkButton(foot, text="Cancel", width=90, height=34,
                      fg_color=("#252535","#252535"), hover_color=("#353548","#353548"),
                      command=self.destroy).pack(side="right", padx=(4, 0))
        ctk.CTkButton(foot, text="Save Snippet", width=120, height=34,
                      font=ctk.CTkFont(size=13, weight="bold"),
                      command=self._save).pack(side="right")

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
