"""
Quick Notes — floating editor window.

Features
────────
• File-based storage (one UTF-8 .txt per note under %APPDATA%/HotkeyTool/notes/)
• Line-number gutter
• Integrated Find / Replace bar  (Ctrl+F / Ctrl+H to toggle, appears inline below toolbar)
• Status bar  (line · column · character count · word count)
• Word-wrap toggle
• Zoom in / out  (Ctrl+= / Ctrl+-)
• Full undo / redo  (Ctrl+Z / Ctrl+Y)
• Select all  (Ctrl+A)
• Go to line  (Ctrl+G)
• Ctrl+Left / Right  (word navigation that respects line boundaries)
• Auto-save on every keystroke
• Options dialog  (⚙ button)
• Default size  1200 × 800
"""
from __future__ import annotations

import ctypes
import re
import sys
import tkinter as tk
from typing import TYPE_CHECKING, List, Optional

import customtkinter as ctk

from core.notes_manager import (
    NoteFile,
    create_note,
    delete_note,
    load_all,
    load_content,
    rename_note,
    save_content,
)

if TYPE_CHECKING:
    from app import App

_DEFAULT_GEO  = "1200x800"
_MIN_FONT     = 8
_MAX_FONT     = 36
_MATCH_TAG    = "match"
_MATCH_CUR    = "match_cur"

_FONTS = ["Consolas", "Cascadia Code", "Courier New", "Lucida Console"]


def _mk_colors() -> dict:
    """Pull a Notes-specific palette from the global theme tokens.

    Keeping the dict-of-named-colors API so the rest of this file doesn't
    have to change.  All values now come from ui.theme — no more hardcoded
    hex from the old design.
    """
    from ui import theme as _t
    return {
        "bg":          _t.BG_BASE,        # window root
        "editor_bg":   _t.BG_SURFACE,     # text body — slightly less dark, same level
                                          # as the toolbar so it reads as one surface
        "fg":          _t.TEXT_1,
        "gutter_bg":   _t.BG_INPUT,       # gutter darker than editor, subtle contrast
        "gutter_fg":   _t.TEXT_4,
        "cursor":      _t.ACCENT,
        "sel_bg":      _t.ACCENT_BG_2,
        "toolbar_bg":  _t.BG_SURFACE,
        "bar_bg":      _t.BG_SURFACE,
        "btn_bg":      _t.BG_ELEVATED,
        "btn_fg":      _t.TEXT_1,
        "btn_abg":     _t.BG_HOVER,
        "btn_afg":     _t.TEXT_1,
        "add_bg":      _t.SUCCESS_BG,
        "del_bg":      _t.DANGER_BG,
        "wrap_on_bg":  _t.SUCCESS_BG,
        "wrap_on_fg":  _t.SUCCESS,
        "wrap_off_bg": _t.DANGER_BG,
        "wrap_off_fg": _t.DANGER,
        "border":      _t.BORDER_SOFT,
        "match_bg":    _t.WARNING_BG,
        "match_fg":    _t.WARNING,
        "mcur_bg":     _t.ACCENT_DEEP,
        "mcur_fg":     _t.TEXT_1,
        "lbl_fg":      _t.TEXT_2,
        "ent_bg":      _t.BG_INPUT,
        "ent_hi":      _t.BORDER,
        "ent_hia":     _t.ACCENT_MID,
        "cnt_fg":      _t.ACCENT,
        "close_bg":    _t.DANGER_BG,
        "status_fg":   _t.TEXT_3,
        "saved_fg":    _t.WARNING,
    }


class NotesWindow(ctk.CTkToplevel):
    def __init__(self, app: "App") -> None:
        super().__init__()
        self.app      = app
        self._notes:  List[NoteFile] = []
        self._active: Optional[NoteFile] = None
        self._visible         = False
        self._first_show      = True
        self._font_size       = 13
        self._blink_timer: str | None = None
        self._sel_anchor: str | None  = None
        self._font_name       = "Consolas"
        self._wrap_mode       = "word"
        self._find_visible    = False
        self._find_results:   List[str] = []
        self._find_idx        = 0

        self.title("Quick Notes")
        self.minsize(460, 320)
        geo = app.config.settings.notes_geometry
        self.geometry(geo if geo else _DEFAULT_GEO)

        self.protocol("WM_DELETE_WINDOW", self.hide)
        self.bind("<Configure>", self._on_configure)
        self._C = _mk_colors()
        self.configure(fg_color=self._C["bg"])
        self._build()
        self._reload_notes()
        self.withdraw()

        self.after(200, self._apply_window_icon)
        
    # icon
    def _apply_window_icon(self) -> None:
        """Apply the .ico to the title bar and taskbar for this specific window."""
        from utils.resource_path import resource_path
        try:
            ico_path = resource_path("assets/hotkeytool.ico")
            if ico_path.exists():
                # Sets the icon for the title bar
                self.iconbitmap(str(ico_path))
                
                # Ensures Windows uses the app icon for the taskbar group
                if sys.platform == "win32":
                    myappid = 'mycompany.myproduct.subproduct.version'
                    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)
        except Exception as e:
            print(f"NotesWindow icon error: {e}")

    # ── layout ────────────────────────────────────────────────────────────────

    def _build(self) -> None:
        C    = self._C
        from ui import theme as _t
        from ui.widgets import DangerButton, GhostButton, PrimaryButton, SuccessButton

        # ── Header (matches main window's header pattern) ────────────────────
        header = ctk.CTkFrame(self, fg_color=_t.BG_SURFACE,
                              corner_radius=0, height=60)
        header.pack(fill="x", side="top")
        header.pack_propagate(False)
        self._tb = header

        # Brand cluster on the left: title + note dropdown + note CRUD buttons
        left = ctk.CTkFrame(header, fg_color="transparent")
        left.pack(side="left", padx=(18, 0), pady=14)

        ctk.CTkLabel(
            left, text="Quick Notes",
            font=_t.font(14, "bold"), text_color=_t.TEXT_1,
            fg_color="transparent",
        ).pack(side="left", padx=(0, 14))

        # Vertical separator
        ctk.CTkFrame(left, width=1, height=24, fg_color=_t.BORDER,
                     corner_radius=0).pack(side="left", padx=(0, 12))

        self._note_var  = ctk.StringVar()
        self._note_menu = ctk.CTkOptionMenu(
            left, variable=self._note_var, values=["(none)"],
            command=self._on_note_selected, width=220, height=32,
            corner_radius=_t.RADIUS_SM,
            font=_t.font(12), text_color=_t.TEXT_1,
            fg_color=_t.BG_ELEVATED, button_color=_t.BG_HOVER,
            button_hover_color=_t.BORDER_STRONG,
            dropdown_fg_color=_t.BG_ELEVATED,
            dropdown_text_color=_t.TEXT_1,
            dropdown_hover_color=_t.BG_HOVER,
            dropdown_font=_t.font(12),
        )
        self._note_menu.pack(side="left", padx=(0, 8))

        PrimaryButton(left, text="+  New", small=True,
                      command=self._new_note).pack(side="left", padx=2)
        GhostButton(left, text="Rename", small=True,
                    command=self._rename_note).pack(side="left", padx=2)
        DangerButton(left, text="Delete", small=True,
                     command=self._delete_note).pack(side="left", padx=2)

        # Right-side action cluster
        actions = ctk.CTkFrame(header, fg_color="transparent")
        actions.pack(side="right", padx=(0, 16), pady=14)

        GhostButton(actions, text="⚙", small=True, width=34,
                    command=self._open_options).pack(side="right", padx=(6, 0))
        GhostButton(actions, text="A+", small=True, width=34,
                    command=self._zoom_in).pack(side="right", padx=2)
        GhostButton(actions, text="A−", small=True, width=34,
                    command=self._zoom_out).pack(side="right", padx=2)

        # Wrap toggle — swaps between SuccessButton/DangerButton styles
        self._wrap_btn_tk = SuccessButton(
            actions, text="Wrap on", small=True, command=self._toggle_wrap)
        self._wrap_btn_tk.pack(side="right", padx=(6, 2))

        GhostButton(actions, text="Find", small=True,
                    command=self._toggle_find).pack(side="right", padx=2)
        GhostButton(actions, text="Go to line", small=True,
                    command=self._go_to_line).pack(side="right", padx=2)

        # 1-px header underline (matches main window)
        ctk.CTkFrame(self, height=1, fg_color=_t.BORDER_SOFT,
                     corner_radius=0).pack(fill="x", side="top")

        # Shared font handles for the rest of _build (find bar / status bar)
        _ff      = _t.font_family()
        _mono_ff = _t.mono_family()

        # ── Find / Replace bar (hidden initially, placed between toolbar and editor) ──
        self._find_bar = tk.Frame(self, bg=C["bar_bg"])

        # 1-px divider above find bar (only visible when bar is shown)
        self._find_bar_border = tk.Frame(self._find_bar, height=1, bg=C["border"])
        self._find_bar_border.pack(fill="x", side="top")

        fi = tk.Frame(self._find_bar, bg=C["bar_bg"])
        fi.pack(fill="x", padx=10, pady=8)

        def _lbl(text):
            return tk.Label(fi, text=text, bg=C["bar_bg"], fg=C["lbl_fg"],
                            font=(_ff, 11))

        def _entry(var, w):
            return tk.Entry(fi, textvariable=var, width=w,
                            bg=C["ent_bg"], fg=C["fg"],
                            insertbackground=C["cursor"],
                            relief="flat", font=(_mono_ff, 11),
                            borderwidth=0, highlightthickness=1,
                            highlightbackground=C["ent_hi"],
                            highlightcolor=C["ent_hia"])

        def _fbtn(text, cmd, *, bg=C["btn_bg"], fg=C["btn_fg"], padx=10):
            return tk.Button(fi, text=text, command=cmd,
                             bg=bg, fg=fg, activebackground=C["btn_abg"],
                             relief="flat", bd=0, font=(_ff, 10),
                             cursor="hand2", padx=padx, pady=3)

        _lbl("Find:").pack(side="left")
        self._find_var = tk.StringVar()
        self._find_entry = _entry(self._find_var, 22)
        self._find_entry.pack(side="left", padx=(4, 2))
        self._find_var.trace_add("write", lambda *_: self._do_highlight())
        self._find_entry.bind("<Return>",   lambda e: self._find_step(1))
        self._find_entry.bind("<KP_Enter>", lambda e: self._find_step(1))

        _fbtn("▲", lambda: self._find_step(-1), padx=6).pack(side="left", padx=1)
        _fbtn("▼", lambda: self._find_step(1),  padx=6).pack(side="left", padx=1)

        self._case_var = tk.BooleanVar(value=False)
        tk.Checkbutton(
            fi, text="Aa", variable=self._case_var,
            command=self._do_highlight,
            bg=C["bar_bg"], fg=C["lbl_fg"], selectcolor=C["ent_bg"],
            activebackground=C["bar_bg"], activeforeground=C["btn_afg"],
            relief="flat", bd=0, font=(_ff, 10),
        ).pack(side="left", padx=6)

        self._find_count = tk.Label(fi, text="", bg=C["bar_bg"], fg=C["cnt_fg"],
                                    font=(_ff, 10), width=10, anchor="w")
        self._find_count.pack(side="left", padx=(4, 10))

        _lbl("Replace:").pack(side="left")
        self._repl_var = tk.StringVar()
        self._repl_entry = _entry(self._repl_var, 18)
        self._repl_entry.pack(side="left", padx=(4, 6))
        self._repl_entry.bind("<Return>",   lambda e: self._replace_one())
        self._repl_entry.bind("<KP_Enter>", lambda e: self._replace_one())

        _fbtn("Replace",     self._replace_one,
              bg=C["add_bg"], fg=C["wrap_on_fg"]).pack(side="left", padx=2)
        _fbtn("Replace All", self._replace_all,
              bg=C["add_bg"], fg=C["wrap_on_fg"]).pack(side="left", padx=1)
        _fbtn("✕", self._hide_find,
              bg=C["close_bg"], fg=C["wrap_off_fg"], padx=8
              ).pack(side="right", padx=4)

        # ── Status bar (matches main window's status bar) ──
        sf = tk.Frame(self, bg=C["bar_bg"], height=28)
        sf.pack(fill="x", side="bottom")
        sf.pack_propagate(False)
        # top border line
        tk.Frame(sf, height=1, bg=C["border"]).pack(fill="x", side="top")
        self._status = tk.Label(
            sf, text="Ln 1, Col 1  |  0 chars  |  0 words",
            bg=C["bar_bg"], fg=C["status_fg"], font=(_ff, 10), anchor="w",
        )
        self._status.pack(side="left", padx=14)
        self._saved_lbl = tk.Label(
            sf, text="",
            bg=C["bar_bg"], fg=C["saved_fg"], font=(_ff, 10), anchor="e",
        )
        self._saved_lbl.pack(side="right", padx=14)

        # ── Editor area ──
        editor = tk.Frame(self, bg=C["gutter_bg"])
        editor.pack(fill="both", expand=True)
        self._editor_frame = editor

        self._linenums = tk.Text(
            editor,
            width=4, padx=6, pady=4,
            bg=C["gutter_bg"], fg=C["gutter_fg"],
            selectbackground=C["gutter_bg"], selectforeground=C["gutter_fg"],
            font=(self._font_name, self._font_size),
            state="disabled", cursor="arrow",
            relief="flat", borderwidth=0, wrap="none",
        )
        self._linenums.pack(side="left", fill="y")
        tk.Frame(editor, width=1, bg=C["border"]).pack(side="left", fill="y")

        self._text = tk.Text(
            editor,
            padx=14, pady=8,
            bg=C["editor_bg"], fg=C["fg"],
            insertbackground=C["cursor"],
            selectbackground=C["sel_bg"], selectforeground=C["fg"],
            font=(self._font_name, self._font_size),
            relief="flat", borderwidth=0,
            wrap=self._wrap_mode,
            undo=True, maxundo=-1,
            tabs=("1c",),
            insertontime=600, insertofftime=0,   # solid cursor; blink only when idle
        )
        self._text.tag_configure(_MATCH_TAG,
                                 background=C["match_bg"], foreground=C["match_fg"])
        self._text.tag_configure(_MATCH_CUR,
                                 background=C["mcur_bg"], foreground=C["mcur_fg"])

        vsb = ctk.CTkScrollbar(editor, command=self._scroll_both)
        vsb.pack(side="right", fill="y")

        # Re-render gutter on width changes (wrap points shift with widget width)
        self._text.bind("<Configure>",
                        lambda e: self.after_idle(self._update_linenums),
                        add="+")
        self._text.configure(yscrollcommand=lambda *a: (
            vsb.set(*a),
            self._linenums.yview_moveto(a[0]),
        ))
        self._text.pack(side="left", fill="both", expand=True)

        # ── Key / event bindings ──
        self._text.bind("<<Modified>>",      self._on_modified)
        self._text.bind("<KeyRelease>",      self._on_key_release)
        self._text.bind("<ButtonRelease>",   self._on_mouse_release)
        self._text.bind("<Control-z>",         lambda e: self._undo())
        self._text.bind("<Control-Z>",         lambda e: self._undo())
        self._text.bind("<Control-y>",         lambda e: self._redo())
        self._text.bind("<Control-Y>",         lambda e: self._redo())
        self._text.bind("<Control-a>",         lambda e: (self._select_all(), "break"))
        self._text.bind("<Control-A>",         lambda e: (self._select_all(), "break"))
        self._text.bind("<Control-f>",         lambda e: (self._show_find(), "break"))
        self._text.bind("<Control-F>",         lambda e: (self._show_find(), "break"))
        self._text.bind("<Control-h>",         lambda e: (self._show_find(), "break"))
        self._text.bind("<Control-H>",         lambda e: (self._show_find(), "break"))
        self._text.bind("<Control-g>",         lambda e: (self._go_to_line(), "break"))
        self._text.bind("<Control-G>",         lambda e: (self._go_to_line(), "break"))
        self._text.bind("<Control-minus>",     lambda e: (self._zoom_out(), "break"))
        self._text.bind("<Control-equal>",     lambda e: (self._zoom_in(),  "break"))
        self._text.bind("<Control-plus>",      lambda e: (self._zoom_in(),  "break"))
        self._text.bind("<Control-Right>",       self._ctrl_right)
        self._text.bind("<Control-Left>",        self._ctrl_left)
        self._text.bind("<Control-Up>",          self._ctrl_up)
        self._text.bind("<Control-Down>",        self._ctrl_down)
        self._text.bind("<Control-Shift-Right>", self._ctrl_shift_right)
        self._text.bind("<Control-Shift-Left>",  self._ctrl_shift_left)
        self._text.bind("<Control-Shift-Up>",    self._ctrl_shift_up)
        self._text.bind("<Control-Shift-Down>",  self._ctrl_shift_down)
        self._text.bind("<Control-d>",         lambda e: self._duplicate_line())
        self._text.bind("<Control-D>",         lambda e: self._duplicate_line())
        self._text.bind("<Control-Shift-k>",   lambda e: self._delete_line())
        self._text.bind("<Control-Shift-K>",   lambda e: self._delete_line())
        self._text.bind("<Shift-Delete>",      lambda e: self._delete_line())
        self._text.bind("<Control-Return>",    lambda e: self._open_line_below())
        self._text.bind("<Alt-Up>",            lambda e: self._move_line_up())
        self._text.bind("<Alt-Down>",          lambda e: self._move_line_down())
        self._text.bind("<Escape>",            self._on_escape)
        # Window-level bindings (when focus is on other controls)
        self.bind("<Control-f>", lambda e: self._show_find())
        self.bind("<Control-F>", lambda e: self._show_find())
        self.bind("<Control-h>", lambda e: self._show_find())
        self.bind("<Control-H>", lambda e: self._show_find())
        self.bind("<Escape>",    lambda e: self._on_escape())

    # ── note management ───────────────────────────────────────────────────────

    def _reload_notes(self) -> None:
        self._notes = load_all()
        if not self._notes:
            self._notes = [create_note("Quick Note")]
        self._refresh_menu()
        self._load_note(self._notes[0])

    def _refresh_menu(self) -> None:
        names = [n.name for n in self._notes] or ["(none)"]
        self._note_menu.configure(values=names)

    def _load_note(self, note: NoteFile) -> None:
        self._save_active()
        self._active = note
        self._text.config(state="normal")
        self._text.delete("1.0", "end")
        self._text.insert("1.0", load_content(note))
        self._text.edit_reset()
        self._text.edit_modified(False)
        self._note_var.set(note.name)
        self._update_linenums()
        self._update_status()
        self._saved_lbl.config(text="")

    def _save_active(self) -> None:
        if self._active is not None:
            save_content(self._active, self._text.get("1.0", "end-1c"))

    def _on_note_selected(self, name: str) -> None:
        note = next((n for n in self._notes if n.name == name), None)
        if note and (self._active is None or note.id != self._active.id):
            self._load_note(note)

    def _new_note(self) -> None:
        note = create_note(f"Note {len(self._notes) + 1}")
        self._notes.append(note)
        self._refresh_menu()
        self._load_note(note)

    def _rename_note(self) -> None:
        if not self._active:
            return
        dlg = _InputDialog(self, "Rename Note", "New name:", self._active.name)
        self.wait_window(dlg)
        if dlg.result and dlg.result.strip():
            new_name = dlg.result.strip()
            rename_note(self._active.id, new_name)
            self._active.name = new_name
            self._refresh_menu()
            self._note_var.set(new_name)

    def _delete_note(self) -> None:
        if not self._active or len(self._notes) <= 1:
            return
        delete_note(self._active.id)
        self._notes = [n for n in self._notes if n.id != self._active.id]
        self._active = None
        self._refresh_menu()
        self._load_note(self._notes[0])

    # ── editor events ──────────────────────────────────────────────────────────

    def _on_modified(self, _event=None) -> None:
        if self._text.edit_modified():
            self._saved_lbl.config(text="●")
            self._save_active()
            self._saved_lbl.config(text="")
            self._text.edit_modified(False)

    def _on_activity(self) -> None:
        """Keep cursor solid while the user is active; resume blinking after 1 s of idle."""
        if self._blink_timer:
            self.after_cancel(self._blink_timer)
        self._text.configure(insertofftime=0)
        self._blink_timer = self.after(1000, self._resume_blink)

    def _resume_blink(self) -> None:
        self._blink_timer = None
        self._text.configure(insertofftime=300)

    def _on_key_release(self, _event=None) -> None:
        self._on_activity()
        self._update_linenums()
        self._update_status()
        if self._find_visible and self._find_var.get():
            self._do_highlight()

    def _on_mouse_release(self, _event=None) -> None:
        self._sel_anchor = None
        self._on_activity()
        self._update_status()

    def _on_escape(self, _event=None) -> None:
        if self._find_visible:
            self._hide_find()

    def _select_all(self) -> None:
        self._text.tag_add(tk.SEL, "1.0", "end-1c")
        self._text.mark_set(tk.INSERT, "end-1c")

    def _undo(self, event=None) -> str:
        try:
            self._text.edit_undo()
        except tk.TclError:
            pass
        self._update_linenums()
        self._update_status()
        return "break"

    def _redo(self, event=None) -> str:
        try:
            self._text.edit_redo()
        except tk.TclError:
            pass
        self._update_linenums()
        self._update_status()
        return "break"

    # ── word navigation helpers ───────────────────────────────────────────────

    def _next_word_pos(self, insert: str) -> str | None:
        """Return position of next word start (Windows-style), or None at document end."""
        ln, col = insert.split(".")
        ln, col = int(ln), int(col)
        line = self._text.get(f"{ln}.0", f"{ln}.end")
        n = len(line)
        if col >= n:
            total = int(self._text.index("end-1c").split(".")[0])
            if ln >= total:
                return None
            return f"{ln+1}.0"
        pos = col
        while pos < n and not line[pos].isspace():
            pos += 1
        while pos < n and line[pos].isspace():
            pos += 1
        return f"{ln}.{pos}"

    def _prev_word_pos(self, insert: str) -> str | None:
        """Return position of previous word start (Windows-style), or None at document start."""
        ln, col = insert.split(".")
        ln, col = int(ln), int(col)
        if col == 0:
            if ln <= 1:
                return None
            prev = ln - 1
            prev_line = self._text.get(f"{prev}.0", f"{prev}.end")
            return f"{prev}.{len(prev_line)}"
        line = self._text.get(f"{ln}.0", f"{ln}.end")
        pos = col
        while pos > 0 and line[pos-1].isspace():
            pos -= 1
        while pos > 0 and not line[pos-1].isspace():
            pos -= 1
        return f"{ln}.{pos}"

    def _ctrl_right(self, event=None) -> str:
        """Move to start of next word; clear selection and stored anchor."""
        self._sel_anchor = None
        new_pos = self._next_word_pos(self._text.index(tk.INSERT))
        if new_pos is None:
            return "break"
        self._text.tag_remove(tk.SEL, "1.0", "end")
        self._text.mark_set(tk.INSERT, new_pos)
        self._text.see(tk.INSERT)
        self._update_status()
        return "break"

    def _ctrl_left(self, event=None) -> str:
        """Move to start of previous word; clear selection and stored anchor."""
        self._sel_anchor = None
        new_pos = self._prev_word_pos(self._text.index(tk.INSERT))
        if new_pos is None:
            return "break"
        self._text.tag_remove(tk.SEL, "1.0", "end")
        self._text.mark_set(tk.INSERT, new_pos)
        self._text.see(tk.INSERT)
        self._update_status()
        return "break"

    def _ctrl_shift_right(self, event=None) -> str:
        """Extend selection to start of next word."""
        insert = self._text.index(tk.INSERT)
        if self._sel_anchor is None:
            self._sel_anchor = insert
        new_pos = self._next_word_pos(insert)
        if new_pos is None:
            return "break"
        self._text.mark_set(tk.INSERT, new_pos)
        self._apply_selection(self._sel_anchor, new_pos)
        self._text.see(tk.INSERT)
        self._update_status()
        return "break"

    def _ctrl_shift_left(self, event=None) -> str:
        """Extend selection to start of previous word."""
        insert = self._text.index(tk.INSERT)
        if self._sel_anchor is None:
            self._sel_anchor = insert
        new_pos = self._prev_word_pos(insert)
        if new_pos is None:
            return "break"
        self._text.mark_set(tk.INSERT, new_pos)
        self._apply_selection(self._sel_anchor, new_pos)
        self._text.see(tk.INSERT)
        self._update_status()
        return "break"

    def _ctrl_up(self, event=None) -> str:
        """Ctrl+Up: move cursor up one line, clear selection and anchor."""
        self._sel_anchor = None
        self._text.tag_remove(tk.SEL, "1.0", "end")
        self._text.mark_set(tk.INSERT, "insert - 1 lines")
        self._text.see(tk.INSERT)
        self._update_status()
        return "break"

    def _ctrl_down(self, event=None) -> str:
        """Ctrl+Down: move cursor down one line, clear selection and anchor."""
        self._sel_anchor = None
        self._text.tag_remove(tk.SEL, "1.0", "end")
        self._text.mark_set(tk.INSERT, "insert + 1 lines")
        self._text.see(tk.INSERT)
        self._update_status()
        return "break"

    def _ctrl_shift_up(self, event=None) -> str:
        """Extend selection up one line."""
        insert = self._text.index(tk.INSERT)
        if self._sel_anchor is None:
            self._sel_anchor = insert
        new_pos = self._text.index("insert - 1 lines")
        self._text.mark_set(tk.INSERT, new_pos)
        self._apply_selection(self._sel_anchor, new_pos)
        self._text.see(tk.INSERT)
        self._update_status()
        return "break"

    def _ctrl_shift_down(self, event=None) -> str:
        """Extend selection down one line."""
        insert = self._text.index(tk.INSERT)
        if self._sel_anchor is None:
            self._sel_anchor = insert
        new_pos = self._text.index("insert + 1 lines")
        self._text.mark_set(tk.INSERT, new_pos)
        self._apply_selection(self._sel_anchor, new_pos)
        self._text.see(tk.INSERT)
        self._update_status()
        return "break"

    def _apply_selection(self, anchor: str, cursor: str) -> None:
        self._text.tag_remove(tk.SEL, "1.0", "end")
        if self._text.compare(anchor, "<", cursor):
            self._text.tag_add(tk.SEL, anchor, cursor)
        elif self._text.compare(anchor, ">", cursor):
            self._text.tag_add(tk.SEL, cursor, anchor)

    def _duplicate_line(self, event=None) -> str:
        """Ctrl+D: duplicate the current line below."""
        insert     = self._text.index(tk.INSERT)
        ln, col    = insert.split(".")
        line_start = self._text.index(f"{insert} linestart")
        line_end   = self._text.index(f"{insert} lineend")
        content    = self._text.get(line_start, line_end)
        self._text.insert(line_end, "\n" + content)
        self._text.mark_set(tk.INSERT, f"{int(ln)+1}.{col}")
        self._text.see(tk.INSERT)
        self._update_linenums()
        self._update_status()
        return "break"

    def _delete_line(self, event=None) -> str:
        """Ctrl+Shift+K: delete the current line."""
        insert     = self._text.index(tk.INSERT)
        line_start = self._text.index(f"{insert} linestart")
        # Delete through the newline; fall back to just the line if last line
        try:
            after_newline = self._text.index(f"{insert} lineend + 1c")
            self._text.delete(line_start, after_newline)
        except tk.TclError:
            self._text.delete(line_start, f"{insert} lineend")
        self._update_linenums()
        self._update_status()
        return "break"

    def _open_line_below(self, event=None) -> str:
        """Ctrl+Enter: insert a new blank line below, move cursor there."""
        insert   = self._text.index(tk.INSERT)
        line_end = self._text.index(f"{insert} lineend")
        self._text.mark_set(tk.INSERT, line_end)
        self._text.insert(tk.INSERT, "\n")
        self._text.see(tk.INSERT)
        self._update_linenums()
        self._update_status()
        return "break"

    def _move_line_up(self, event=None) -> str:
        """Alt+Up: swap current line with the line above."""
        insert = self._text.index(tk.INSERT)
        ln, col = insert.split(".")
        ln = int(ln)
        if ln <= 1:
            return "break"
        cur_start  = self._text.index(f"{ln}.0")
        cur_end    = self._text.index(f"{ln}.0 lineend")
        prev_start = self._text.index(f"{ln-1}.0")
        prev_end   = self._text.index(f"{ln-1}.0 lineend")
        cur_text   = self._text.get(cur_start, cur_end)
        prev_text  = self._text.get(prev_start, prev_end)
        # Replace both lines atomically
        self._text.delete(prev_start, cur_end)
        self._text.insert(prev_start, cur_text + "\n" + prev_text)
        self._text.mark_set(tk.INSERT, f"{ln-1}.{col}")
        self._text.see(tk.INSERT)
        self._update_linenums()
        self._update_status()
        return "break"

    def _move_line_down(self, event=None) -> str:
        """Alt+Down: swap current line with the line below."""
        insert = self._text.index(tk.INSERT)
        ln, col = insert.split(".")
        ln     = int(ln)
        total  = int(self._text.index("end-1c").split(".")[0])
        if ln >= total:
            return "break"
        cur_start  = self._text.index(f"{ln}.0")
        cur_end    = self._text.index(f"{ln}.0 lineend")
        next_start = self._text.index(f"{ln+1}.0")
        next_end   = self._text.index(f"{ln+1}.0 lineend")
        cur_text   = self._text.get(cur_start, cur_end)
        next_text  = self._text.get(next_start, next_end)
        self._text.delete(cur_start, next_end)
        self._text.insert(cur_start, next_text + "\n" + cur_text)
        self._text.mark_set(tk.INSERT, f"{ln+1}.{col}")
        self._text.see(tk.INSERT)
        self._update_linenums()
        self._update_status()
        return "break"

    def _update_linenums(self) -> None:
        """Render one sequential gutter number per VISUAL row.

        With wrap=word, each wrapped row gets its own line number — a line
        that wraps to 3 visual rows shows up as three separate gutter
        entries.  With wrap=none, display rows equal logical lines, so the
        gutter just shows 1..N as expected.

        `Go to line N` is interpreted against this same numbering (see
        `_go_to_line`) and converts N to the underlying text index via
        Tk's `+ N display lines` offset.
        """
        self._linenums.config(state="normal")
        self._linenums.delete("1.0", "end")
        total = self._total_display_lines()
        self._linenums.insert(
            "1.0", "\n".join(str(i) for i in range(1, total + 1)))
        self._linenums.config(state="disabled")
        self._linenums.yview_moveto(self._text.yview()[0])

    def _total_display_lines(self) -> int:
        """Total visual rows in the text widget (1 minimum)."""
        try:
            n = self._text.count("1.0", "end-1c", "displaylines")
            if isinstance(n, (tuple, list)):
                n = n[0] if n else 0
            n = int(n) if n is not None else 0
        except (tk.TclError, Exception):
            n = int(self._text.index("end-1c").split(".")[0])
        return max(1, n)

    def _update_status(self, _event=None) -> None:
        # Visual row of the cursor (matches the gutter numbering).
        try:
            v = self._text.count("1.0", "insert", "displaylines")
            if isinstance(v, (tuple, list)):
                v = v[0] if v else 0
            ln = (int(v) if v is not None else 0) + 1
        except (tk.TclError, Exception):
            ln = int(self._text.index("insert").split(".")[0])

        # Column within the current visual row.
        try:
            row_start = self._text.index("insert display linestart")
            c = self._text.count(row_start, "insert", "chars")
            if isinstance(c, (tuple, list)):
                c = c[0] if c else 0
            col = int(c) if c is not None else 0
        except (tk.TclError, Exception):
            col = int(self._text.index("insert").split(".")[1])

        content = self._text.get("1.0", "end-1c")
        chars   = len(content)
        words   = len(content.split()) if content.strip() else 0
        total   = self._total_display_lines()
        self._status.config(
            text=f"Ln {ln}, Col {col + 1}  |  {chars} chars  |  {words} words  |  {total} lines"
        )

    # ── find / replace ────────────────────────────────────────────────────────

    def _show_find(self) -> None:
        if not self._find_visible:
            self._find_bar.pack(fill="x", before=self._editor_frame)
            self._find_visible = True
        self._find_entry.focus_set()
        self._find_entry.select_range(0, "end")
        try:
            sel = self._text.get(tk.SEL_FIRST, tk.SEL_LAST)
            if sel and "\n" not in sel:
                self._find_var.set(sel)
                self._find_entry.select_range(0, "end")
                self._do_highlight()
        except tk.TclError:
            pass

    def _hide_find(self) -> None:
        if self._find_visible:
            self._find_bar.pack_forget()
            self._find_visible = False
        self._text.tag_remove(_MATCH_TAG, "1.0", "end")
        self._text.tag_remove(_MATCH_CUR, "1.0", "end")
        self._find_count.config(text="")
        self._text.focus_set()

    def _toggle_find(self) -> None:
        self._hide_find() if self._find_visible else self._show_find()

    def _do_highlight(self) -> None:
        self._text.tag_remove(_MATCH_TAG, "1.0", "end")
        self._text.tag_remove(_MATCH_CUR, "1.0", "end")
        self._find_results.clear()
        pattern = self._find_var.get()
        if not pattern:
            self._find_count.config(text="")
            return
        nocase = not self._case_var.get()
        start  = "1.0"
        while True:
            pos = self._text.search(pattern, start, stopindex="end",
                                    nocase=nocase, regexp=False)
            if not pos:
                break
            end_i = f"{pos}+{len(pattern)}c"
            self._text.tag_add(_MATCH_TAG, pos, end_i)
            self._find_results.append(pos)
            start = end_i
        count = len(self._find_results)
        if count == 0:
            self._find_count.config(text="not found", fg="#cc5555")
        else:
            self._find_count.config(text=f"{count} found", fg=self._C["cnt_fg"])
            self._find_idx = 0
            self._jump_to_match(0)

    def _find_step(self, direction: int) -> None:
        if not self._find_results:
            self._do_highlight()
            return
        self._find_idx = (self._find_idx + direction) % len(self._find_results)
        self._jump_to_match(self._find_idx)

    def _jump_to_match(self, idx: int) -> None:
        self._text.tag_remove(_MATCH_CUR, "1.0", "end")
        pos     = self._find_results[idx]
        pattern = self._find_var.get()
        end_i   = f"{pos}+{len(pattern)}c"
        self._text.tag_add(_MATCH_CUR, pos, end_i)
        self._text.see(pos)
        self._text.mark_set(tk.INSERT, pos)
        self._find_count.config(
            text=f"{idx+1}/{len(self._find_results)}", fg=self._C["cnt_fg"])

    def _replace_one(self) -> None:
        if not self._find_results:
            self._do_highlight()
            return
        idx     = self._find_idx % max(len(self._find_results), 1)
        pos     = self._find_results[idx]
        pattern = self._find_var.get()
        repl    = self._repl_var.get()
        self._text.delete(pos, f"{pos}+{len(pattern)}c")
        self._text.insert(pos, repl)
        self._save_active()
        self._do_highlight()

    def _replace_all(self) -> None:
        pattern = self._find_var.get()
        if not pattern:
            return
        nocase  = not self._case_var.get()
        content = self._text.get("1.0", "end-1c")
        flags   = re.IGNORECASE if nocase else 0
        new_content = re.sub(re.escape(pattern), self._repl_var.get(),
                             content, flags=flags)
        if new_content == content:
            return
        self._text.delete("1.0", "end")
        self._text.insert("1.0", new_content)
        self._save_active()
        self._do_highlight()

    # ── go to line ────────────────────────────────────────────────────────────

    def _go_to_line(self) -> None:
        total = self._total_display_lines()
        dlg = _InputDialog(self, "Go to Line",
                           f"Line number (1-{total}):", "")
        self.wait_window(dlg)
        if dlg.result and dlg.result.strip().isdigit():
            n = max(1, min(int(dlg.result.strip()), total))
            # Visual row N → text index via "+ N display lines" from "1.0".
            try:
                target = self._text.index(f"1.0 + {n - 1} display lines")
            except tk.TclError:
                target = f"{n}.0"
            self._text.mark_set(tk.INSERT, target)
            self._text.see(target)
            self._text.focus_set()
            self._update_status()

    # ── zoom / wrap ───────────────────────────────────────────────────────────

    def _zoom_in(self) -> None:
        if self._font_size < _MAX_FONT:
            self._font_size += 1
            self._apply_font()

    def _zoom_out(self) -> None:
        if self._font_size > _MIN_FONT:
            self._font_size -= 1
            self._apply_font()

    def _apply_font(self) -> None:
        f = (self._font_name, self._font_size)
        self._text.configure(font=f)
        self._linenums.configure(font=f)
        self._update_linenums()

    def _toggle_wrap(self) -> None:
        from ui import theme as _t
        self._wrap_mode = "none" if self._wrap_mode == "word" else "word"
        self._text.configure(wrap=self._wrap_mode)
        if self._wrap_mode == "word":
            self._wrap_btn_tk.configure(
                text="Wrap on",
                fg_color=_t.SUCCESS_BG, hover_color=_t.SUCCESS_BORDER,
                text_color=_t.SUCCESS, border_color=_t.SUCCESS_BORDER)
        else:
            self._wrap_btn_tk.configure(
                text="Wrap off",
                fg_color=_t.DANGER_BG, hover_color=_t.DANGER_BORDER,
                text_color=_t.DANGER, border_color=_t.DANGER_BORDER)
        # Wrap mode change alters display rows — rebuild gutter alignment.
        self.after(0, self._update_linenums)

    # ── options dialog ────────────────────────────────────────────────────────

    def _open_options(self) -> None:
        _OptionsDialog(self)

    # ── scroll sync ───────────────────────────────────────────────────────────

    def _scroll_both(self, *args) -> None:
        self._text.yview(*args)
        self._linenums.yview(*args)

    # ── geometry / visibility ─────────────────────────────────────────────────

    def _on_configure(self, _event=None) -> None:
        if self.winfo_viewable():
            self.app.config.settings.notes_geometry = self.geometry()

    def show(self) -> None:
        self._visible = True
        self.deiconify()
        self.update_idletasks()             # let the window render before focusing
        self.wm_attributes("-topmost", True)
        self.lift()
        self._focus_text()
        self.after(80,  self._focus_text)
        self.after(300, self._focus_text)
        if self._first_show:
            # On cold boot / post-sleep Windows denies focus to background
            # processes for a while.  Keep retrying and stay topmost longer.
            self._first_show = False
            self.after(700,  self._focus_text)
            self.after(1400, self._focus_text)
            self.after(2500, self._focus_text)
            self.after(4000, lambda: self.wm_attributes("-topmost", False))
        else:
            self.after(700, self._focus_text)
            self.after(900, lambda: self.wm_attributes("-topmost", False))

    def hide(self) -> None:
        self._visible = False
        self._save_active()
        if self.winfo_viewable():
            self.app.config.settings.notes_geometry = self.geometry()
        self.app.save_config_only()
        self.withdraw()

    def toggle(self) -> None:
        if self._visible:
            self.hide()
        else:
            self.show()

    def _focus_text(self) -> None:
        # SetForegroundWindow alone is denied to background processes (this is
        # what makes the Notes window stay un-focused after cold boot or
        # post-sleep).  The reliable bypass is AttachThreadInput — temporarily
        # merging our input queue with the current foreground thread's lets
        # SetForegroundWindow succeed.  Then SetFocus on the text widget's
        # native HWND drops the keyboard caret directly inside the editor.
        try:
            import ctypes
            from ctypes import wintypes
            user32   = ctypes.windll.user32
            kernel32 = ctypes.windll.kernel32

            user32.GetWindowThreadProcessId.restype  = wintypes.DWORD
            user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND,
                                                        ctypes.POINTER(wintypes.DWORD)]
            user32.AttachThreadInput.argtypes = [wintypes.DWORD, wintypes.DWORD,
                                                 wintypes.BOOL]

            target_hwnd = self.winfo_id()
            text_hwnd   = self._text.winfo_id()
            fg_hwnd     = user32.GetForegroundWindow()
            cur_tid     = kernel32.GetCurrentThreadId()

            attached = False
            fg_tid   = 0
            if fg_hwnd and fg_hwnd != target_hwnd:
                fg_tid = user32.GetWindowThreadProcessId(fg_hwnd, None)
                if fg_tid and fg_tid != cur_tid:
                    if user32.AttachThreadInput(cur_tid, fg_tid, True):
                        attached = True
            try:
                user32.BringWindowToTop(target_hwnd)
                user32.SetForegroundWindow(target_hwnd)
                user32.SetFocus(text_hwnd)
            finally:
                if attached:
                    user32.AttachThreadInput(cur_tid, fg_tid, False)
        except Exception:
            pass
        # Tkinter-side focus assertion (sets the widget's internal focus mark)
        try:
            self.focus_force()
            self._text.focus_force()
        except Exception:
            pass


# ── Options dialog ────────────────────────────────────────────────────────────

class _OptionsDialog(ctk.CTkToplevel):
    def __init__(self, notes_win: NotesWindow) -> None:
        from ui import theme as _t
        super().__init__(notes_win, fg_color=_t.BG_SURFACE)
        self._nw = notes_win
        self.title("Quick Notes — Options")
        self.resizable(True, True)
        self.wm_attributes("-topmost", True)
        self.configure(fg_color=_t.BG_SURFACE)
        self._build()
        self.update_idletasks()
        self.geometry(f"440x{max(self.winfo_reqheight() + 30, 420)}")
        self.after(120, self.grab_set)
        from utils.resource_path import apply_window_icon
        self.after(200, lambda: apply_window_icon(self))
        self.lift()

    def _build(self) -> None:
        from ui import theme as _t
        from ui.widgets import GhostButton, PrimaryButton
        pad = {"padx": 20, "pady": 6}
        _entry_kw = dict(fg_color=_t.BG_INPUT, border_color=_t.BORDER,
                         border_width=1, text_color=_t.TEXT_1)
        _opt_kw = dict(fg_color=_t.BG_ELEVATED, button_color=_t.BG_HOVER,
                       button_hover_color=_t.BORDER_STRONG,
                       text_color=_t.TEXT_1, dropdown_fg_color=_t.BG_ELEVATED,
                       dropdown_text_color=_t.TEXT_1,
                       dropdown_hover_color=_t.BG_HOVER)

        ctk.CTkLabel(self, text="Font", font=_t.font(13, "bold"),
                     text_color=_t.TEXT_1,
                     anchor="w").pack(fill="x", padx=20, pady=(16, 2))

        font_row = ctk.CTkFrame(self, fg_color="transparent")
        font_row.pack(fill="x", **pad)
        ctk.CTkLabel(font_row, text="Family:", width=80, anchor="w",
                     font=_t.font(12), text_color=_t.TEXT_2
                     ).pack(side="left")
        self._font_var = ctk.StringVar(value=self._nw._font_name)
        ctk.CTkOptionMenu(font_row, variable=self._font_var,
                          values=_FONTS, width=200, height=30,
                          font=_t.font(12), **_opt_kw).pack(side="left", padx=8)

        size_row = ctk.CTkFrame(self, fg_color="transparent")
        size_row.pack(fill="x", **pad)
        ctk.CTkLabel(size_row, text="Size:", width=80, anchor="w",
                     font=_t.font(12), text_color=_t.TEXT_2
                     ).pack(side="left")
        self._size_var = ctk.StringVar(value=str(self._nw._font_size))
        ctk.CTkEntry(size_row, textvariable=self._size_var,
                     width=70, height=30, font=_t.font(12),
                     **_entry_kw).pack(side="left", padx=8)

        ctk.CTkLabel(self, text="Window Size",
                     font=_t.font(13, "bold"), text_color=_t.TEXT_1,
                     anchor="w").pack(fill="x", padx=20, pady=(14, 2))

        preset_row = ctk.CTkFrame(self, fg_color="transparent")
        preset_row.pack(fill="x", **pad)
        for label, geo in (("820x580", "820x580"), ("1200x800", "1200x800"),
                           ("1400x900", "1400x900"), ("1600x1000", "1600x1000")):
            GhostButton(preset_row, text=label, small=True,
                        command=lambda g=geo: self._apply_geo(g)
                        ).pack(side="left", padx=3)

        custom_row = ctk.CTkFrame(self, fg_color="transparent")
        custom_row.pack(fill="x", **pad)
        ctk.CTkLabel(custom_row, text="Custom:", width=70, anchor="w",
                     font=_t.font(12), text_color=_t.TEXT_2).pack(side="left")
        current = self._nw.geometry().split("+")[0]
        self._geo_var = ctk.StringVar(value=current)
        ctk.CTkEntry(custom_row, textvariable=self._geo_var,
                     width=130, height=30, font=_t.font(12),
                     placeholder_text="1200x800",
                     placeholder_text_color=_t.TEXT_3,
                     **_entry_kw).pack(side="left", padx=6)
        GhostButton(custom_row, text="Apply", small=True,
                    command=lambda: self._apply_geo(self._geo_var.get())
                    ).pack(side="left", padx=4)

        btn_row = ctk.CTkFrame(self, fg_color="transparent")
        btn_row.pack(pady=18)
        PrimaryButton(btn_row, text="OK", command=self._ok
                      ).pack(side="left", padx=6)
        GhostButton(btn_row, text="Cancel", command=self.destroy
                    ).pack(side="left", padx=6)

    def _apply_geo(self, geo: str) -> None:
        try:
            w, h = geo.split("x")
            self._nw.geometry(f"{int(w)}x{int(h)}")
        except Exception:
            pass

    def _ok(self) -> None:
        fname = self._font_var.get()
        try:
            fsize = max(_MIN_FONT, min(_MAX_FONT, int(self._size_var.get())))
        except ValueError:
            fsize = self._nw._font_size
        self._nw._font_name = fname
        self._nw._font_size = fsize
        self._nw._apply_font()
        self.destroy()


# ── small input dialog ────────────────────────────────────────────────────────

class _InputDialog(ctk.CTkToplevel):
    def __init__(self, parent, title: str, label: str, initial: str = "") -> None:
        from ui import theme as _t
        from ui.widgets import GhostButton, PrimaryButton
        super().__init__(parent, fg_color=_t.BG_SURFACE)
        self.result: str | None = None
        self.title(title)
        self.geometry("340x150")
        self.resizable(False, False)
        self.wm_attributes("-topmost", True)
        self.configure(fg_color=_t.BG_SURFACE)

        ctk.CTkLabel(self, text=label, font=_t.font(13),
                     text_color=_t.TEXT_1).pack(padx=18, pady=(16, 6),
                                                anchor="w")
        self._var = ctk.StringVar(value=initial)
        e = ctk.CTkEntry(self, textvariable=self._var, width=300, height=32,
                         fg_color=_t.BG_INPUT, border_color=_t.BORDER,
                         border_width=1, text_color=_t.TEXT_1,
                         font=_t.font(12))
        e.pack(padx=18)
        e.bind("<Return>", lambda _: self._ok())

        row = ctk.CTkFrame(self, fg_color="transparent")
        row.pack(pady=12)
        PrimaryButton(row, text="OK", command=self._ok
                      ).pack(side="left", padx=4)
        GhostButton(row, text="Cancel", command=self.destroy
                    ).pack(side="left", padx=4)

        self.after(120, self.grab_set)
        from utils.resource_path import apply_window_icon
        self.after(200, lambda: apply_window_icon(self))
        self.lift()
        e.focus_set()

    def _ok(self) -> None:
        self.result = self._var.get()
        self.destroy()
