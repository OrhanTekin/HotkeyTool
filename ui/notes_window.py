"""
Floating quick-notes window. Multiple named notes with auto-save.
Can be shown/hidden without destroying state.
"""
from __future__ import annotations

import tkinter as tk
from typing import TYPE_CHECKING, List

import customtkinter as ctk

if TYPE_CHECKING:
    from app import App
    from core.models import Note


class NotesWindow(ctk.CTkToplevel):
    def __init__(self, app: "App") -> None:
        super().__init__()
        self.app = app
        self._active_note_id: str | None = None
        self._visible = False

        self.title("Quick Notes")
        self.minsize(320, 240)
        self.attributes("-topmost", False)

        geo = app.config.settings.notes_geometry
        self.geometry(geo if geo else "480x400")

        self.protocol("WM_DELETE_WINDOW", self.hide)
        self.bind("<Configure>", self._on_configure)
        self._build()
        self._load_first_note()
        self.withdraw()   # hidden by default (same as StatsWidget)

    # ── layout ────────────────────────────────────────────────────────────────

    def _build(self) -> None:
        # Top bar: note selector + actions
        top = ctk.CTkFrame(self, fg_color=("#0f0f22", "#0f0f22"), height=42)
        top.pack(fill="x")
        top.pack_propagate(False)

        ctk.CTkButton(
            top, text="+", width=30, height=28,
            fg_color=("#163a22", "#163a22"), hover_color=("#1e4a2a", "#1e4a2a"),
            font=ctk.CTkFont(size=14, weight="bold"),
            command=self._new_note,
        ).pack(side="left", padx=(6, 2), pady=6)

        self._note_var = ctk.StringVar()
        self._note_menu = ctk.CTkOptionMenu(
            top, variable=self._note_var,
            values=self._note_names(),
            command=self._on_note_selected,
            width=180, height=28,
        )
        self._note_menu.pack(side="left", padx=4, pady=6)

        ctk.CTkButton(
            top, text="Rename", width=70, height=28,
            fg_color=("#1e2a3a", "#1e2a3a"), hover_color=("#2a3a4a", "#2a3a4a"),
            font=ctk.CTkFont(size=11),
            command=self._rename_note,
        ).pack(side="left", padx=2, pady=6)

        ctk.CTkButton(
            top, text="Delete", width=60, height=28,
            fg_color=("#5c1a1a", "#5c1a1a"), hover_color=("#7a2222", "#7a2222"),
            font=ctk.CTkFont(size=11),
            command=self._delete_note,
        ).pack(side="left", padx=2, pady=6)

        # Text area
        self._text = ctk.CTkTextbox(
            self,
            font=ctk.CTkFont(size=13, family="Consolas"),
            wrap="word",
        )
        self._text.pack(fill="both", expand=True, padx=6, pady=6)
        self._text.bind("<KeyRelease>", self._on_text_change)

    # ── note management ───────────────────────────────────────────────────────

    def _note_names(self) -> List[str]:
        return [n.name for n in self.app.config.notes] or ["(none)"]

    def _load_first_note(self) -> None:
        notes = self.app.config.notes
        if notes:
            self._load_note(notes[0])
        self._refresh_menu()

    def _load_note(self, note: "Note") -> None:
        self._save_current()
        self._active_note_id = note.id
        self._text.delete("1.0", "end")
        self._text.insert("1.0", note.content)
        self._note_var.set(note.name)

    def _save_current(self) -> None:
        if self._active_note_id is None:
            return
        note = next((n for n in self.app.config.notes if n.id == self._active_note_id), None)
        if note:
            note.content = self._text.get("1.0", "end-1c")
            self.app.save_config_only()

    def _refresh_menu(self) -> None:
        names = self._note_names()
        self._note_menu.configure(values=names)

    def _on_note_selected(self, name: str) -> None:
        note = next((n for n in self.app.config.notes if n.name == name), None)
        if note:
            self._load_note(note)

    def _on_text_change(self, _event=None) -> None:
        self._save_current()

    def _new_note(self) -> None:
        from core.models import Note
        note = Note.new(f"Note {len(self.app.config.notes) + 1}")
        self.app.config.notes.append(note)
        self._refresh_menu()
        self._load_note(note)

    def _rename_note(self) -> None:
        if not self._active_note_id:
            return
        note = next((n for n in self.app.config.notes if n.id == self._active_note_id), None)
        if not note:
            return
        dialog = _InputDialog(self, "Rename Note", "New name:", note.name)
        self.wait_window(dialog)
        new_name = dialog.result
        if new_name and new_name.strip():
            note.name = new_name.strip()
            self._refresh_menu()
            self._note_var.set(note.name)
            self.app.save_config_only()

    def _delete_note(self) -> None:
        if not self._active_note_id or len(self.app.config.notes) <= 1:
            return
        self.app.config.notes = [
            n for n in self.app.config.notes if n.id != self._active_note_id
        ]
        self._active_note_id = None
        self.app.save_config_only()
        self._refresh_menu()
        self._load_first_note()

    # ── position persistence ──────────────────────────────────────────────────

    def _on_configure(self, _event=None) -> None:
        # Save geometry only when visible (not during withdraw/deiconify)
        if self.winfo_viewable():
            self.app.config.settings.notes_geometry = self.geometry()

    # ── show / hide / toggle  (mirrors StatsWidget exactly) ──────────────────

    def show(self) -> None:
        self._visible = True
        self.deiconify()
        self.lift()
        self.after(80, self._focus_text)

    def hide(self) -> None:
        self._visible = False
        self._save_current()
        self._on_configure()
        self.app.save_config_only()
        self.withdraw()

    def toggle(self) -> None:
        if self._visible:
            self.hide()
        else:
            self.show()

    def _focus_text(self) -> None:
        self.focus_force()
        self._text._textbox.focus_force()


class _InputDialog(ctk.CTkToplevel):
    def __init__(self, parent, title: str, label: str, initial: str = "") -> None:
        super().__init__(parent)
        self.result: str | None = None
        self.title(title)
        self.geometry("320x130")
        self.resizable(False, False)
        self.attributes("-topmost", True)

        ctk.CTkLabel(self, text=label, font=ctk.CTkFont(size=13)).pack(padx=16, pady=(12, 4))
        self._var = ctk.StringVar(value=initial)
        ctk.CTkEntry(self, textvariable=self._var, width=280, height=30).pack(padx=16)

        row = ctk.CTkFrame(self, fg_color="transparent")
        row.pack(pady=10)
        ctk.CTkButton(row, text="OK", width=80, command=self._ok).pack(side="left", padx=4)
        ctk.CTkButton(row, text="Cancel", width=80,
                      fg_color=("#252535","#252535"), hover_color=("#353548","#353548"),
                      command=self.destroy).pack(side="left", padx=4)

        self.after(120, self.grab_set)
        self.lift()

    def _ok(self) -> None:
        self.result = self._var.get()
        self.destroy()
