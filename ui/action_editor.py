"""
A single action row widget used inside BindingEditor.
"""
from __future__ import annotations

from typing import Callable

import customtkinter as ctk

from core.gemini import DEFAULT_PROMPT
from core.models import Action

# ── constants ────────────────────────────────────────────────────────────────

_TYPES = [
    ("Open URL",             "open_url"),
    ("Open App",             "open_app"),
    ("Type Text",            "type_text"),
    ("Run Command",          "run_command"),
    ("Sende Taste(n)",       "send_keys"),
    ("Media Control",        "media_control"),
    ("System Action",        "system_action"),
    ("Toggle Always On Top", "toggle_topmost"),
    ("Replay Macro",         "replay_macro"),
    ("Toggle Stats Widget",  "toggle_stats_widget"),
    ("Show Notes",           "show_notes_window"),
    ("Show Window",          "show_window"),
    ("Wait (ms)",            "wait"),
    ("Color Picker",         "color_picker"),
    ("Transform Text",       "text_transform"),
    ("Gemini: Clipboard",    "gemini_clipboard"),
    ("Gemini: Ask",          "gemini_ask"),
]

# Common keys offered in the send_keys quick-picker
_COMMON_KEYS = [
    ("\u2190 Pfeil Links",  "left"),
    ("\u2192 Pfeil Rechts", "right"),
    ("\u2191 Pfeil Hoch",   "up"),
    ("\u2193 Pfeil Runter", "down"),
    ("Enter",               "enter"),
    ("Escape",              "escape"),
    ("Tab",                 "tab"),
    ("Leertaste",           "space"),
    ("Backspace",           "backspace"),
    ("Delete",              "delete"),
    ("Home",                "home"),
    ("End",                 "end"),
    ("Seite hoch",          "page up"),
    ("Seite runter",        "page down"),
    ("F1",  "f1"),  ("F2",  "f2"),  ("F3",  "f3"),  ("F4",  "f4"),
    ("F5",  "f5"),  ("F6",  "f6"),  ("F7",  "f7"),  ("F8",  "f8"),
    ("F9",  "f9"),  ("F10", "f10"), ("F11", "f11"), ("F12", "f12"),
    ("Drucken (Print Screen)", "print screen"),
    ("Einfügen (Insert)",      "insert"),
    ("Pause",                  "pause"),
    ("Num Lock",               "num lock"),
    ("Scroll Lock",            "scroll lock"),
    ("Caps Lock",              "caps lock"),
    ("Windows-Taste",          "windows"),
    ("Strg+C (Kopieren)",      "ctrl+c"),
    ("Strg+V (Einfügen)",      "ctrl+v"),
    ("Strg+X (Ausschneiden)",  "ctrl+x"),
    ("Strg+Z (Rückgängig)",    "ctrl+z"),
    ("Strg+A (Alles markieren)","ctrl+a"),
    ("Strg+S (Speichern)",     "ctrl+s"),
    ("Alt+F4 (Schließen)",     "alt+f4"),
    ("Win+D (Desktop)",        "windows+d"),
    ("Win+L (Sperren)",        "windows+l"),
]
_COMMON_LABELS     = [lbl for lbl, _ in _COMMON_KEYS]
_COMMON_LABEL_TO_V = {lbl: v for lbl, v in _COMMON_KEYS}
_LABEL_TO_KEY = {lbl: key for lbl, key in _TYPES}
_KEY_TO_LABEL = {key: lbl for lbl, key in _TYPES}

_MEDIA_OPTS = [
    ("Play / Pause",  "play_pause"),
    ("Next Track",    "next_track"),
    ("Prev Track",    "prev_track"),
    ("Stop",          "stop"),
    ("Volume Up",     "volume_up"),
    ("Volume Down",   "volume_down"),
    ("Mute / Unmute", "mute"),
]
_MEDIA_LABEL_TO_KEY = {lbl: k for lbl, k in _MEDIA_OPTS}
_MEDIA_KEY_TO_LABEL = {k: lbl for lbl, k in _MEDIA_OPTS}

_SYSTEM_OPTS = [
    ("Lock Screen", "lock"),
    ("Sleep",       "sleep"),
    ("Shutdown",    "shutdown"),
    ("Restart",     "restart"),
    ("Hibernate",   "hibernate"),
]
_SYS_LABEL_TO_KEY = {lbl: k for lbl, k in _SYSTEM_OPTS}
_SYS_KEY_TO_LABEL = {k: lbl for lbl, k in _SYSTEM_OPTS}


# ── widget ───────────────────────────────────────────────────────────────────

class ActionEditor(ctk.CTkFrame):
    def __init__(
        self,
        parent: ctk.CTkBaseClass,
        action: Action,
        index: int,
        on_remove: Callable[[int], None],
        on_move_up: Callable[[int], None],
        on_move_down: Callable[[int], None],
    ) -> None:
        super().__init__(parent, fg_color=("#151528", "#151528"), corner_radius=8)
        self._action = action
        self.index = index
        self._on_remove = on_remove
        self._on_move_up = on_move_up
        self._on_move_down = on_move_down

        self.type_var  = ctk.StringVar(value=_KEY_TO_LABEL.get(action.type, "Open URL"))
        self.value_var = ctk.StringVar(value=action.value)
        self.delay_var = ctk.StringVar(value=str(max(0, action.delay_after_ms)))

        # sub-vars for option-menu action types (created in _build_value_row)
        self._media_var:       ctk.StringVar | None = None
        self._system_var:      ctk.StringVar | None = None
        self._keys_picker_var: ctk.StringVar | None = None

        self._build()

    # ── build ────────────────────────────────────────────────────────────────

    def _build(self) -> None:
        # ── header row ──
        hdr = ctk.CTkFrame(self, fg_color="transparent")
        hdr.pack(fill="x", padx=10, pady=(8, 2))

        ctk.CTkLabel(
            hdr, text=f"Step {self.index + 1}",
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color=("#6688bb", "#6688bb"), width=54, anchor="w",
        ).pack(side="left")

        self.type_menu = ctk.CTkOptionMenu(
            hdr,
            variable=self.type_var,
            values=[lbl for lbl, _ in _TYPES],
            command=self._on_type_changed,
            width=178, height=28,
            fg_color=("#1e2a3a", "#1e2a3a"),
            button_color=("#2a3a50", "#2a3a50"),
            button_hover_color=("#3a4a60", "#3a4a60"),
        )
        self.type_menu.pack(side="left", padx=(0, 6))

        ctk.CTkButton(
            hdr, text="\u2191", width=26, height=26,
            fg_color=("#252538", "#252538"), hover_color=("#353550", "#353550"),
            font=ctk.CTkFont(size=13),
            command=lambda: self._on_move_up(self.index),
        ).pack(side="left", padx=1)

        ctk.CTkButton(
            hdr, text="\u2193", width=26, height=26,
            fg_color=("#252538", "#252538"), hover_color=("#353550", "#353550"),
            font=ctk.CTkFont(size=13),
            command=lambda: self._on_move_down(self.index),
        ).pack(side="left", padx=1)

        ctk.CTkButton(
            hdr, text="Remove", width=72, height=26,
            fg_color=("#5c1a1a", "#5c1a1a"), hover_color=("#7a2222", "#7a2222"),
            font=ctk.CTkFont(size=11),
            command=lambda: self._on_remove(self.index),
        ).pack(side="right")

        # ── value row (dynamic) ──
        self.value_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.value_frame.pack(fill="x", padx=10, pady=(0, 2))
        self._build_value_row()

        # ── delay row ──
        dfr = ctk.CTkFrame(self, fg_color="transparent")
        dfr.pack(fill="x", padx=10, pady=(0, 8))

        ctk.CTkLabel(
            dfr, text="Delay after (ms):",
            font=ctk.CTkFont(size=11),
            text_color=("#888899", "#888899"), width=112,
        ).pack(side="left")

        ctk.CTkEntry(dfr, textvariable=self.delay_var, width=75, height=26).pack(side="left")

        ctk.CTkLabel(
            dfr, text="  0 = no delay",
            font=ctk.CTkFont(size=10),
            text_color=("#505065", "#505065"),
        ).pack(side="left")

    def _build_value_row(self) -> None:
        for w in self.value_frame.winfo_children():
            w.destroy()
        self._media_var       = None
        self._system_var      = None
        self._keys_picker_var = None

        atype = _LABEL_TO_KEY.get(self.type_var.get(), "open_url")

        if atype in ("open_url", "type_text", "run_command"):
            placeholders = {
                "open_url":    "https://youtube.com",
                "type_text":   "Hello, World!",
                "run_command": "notepad.exe",
            }
            ctk.CTkLabel(
                self.value_frame, text="Value:", width=52,
                font=ctk.CTkFont(size=11),
            ).pack(side="left")
            ctk.CTkEntry(
                self.value_frame, textvariable=self.value_var,
                width=370, height=28,
                placeholder_text=placeholders.get(atype, ""),
            ).pack(side="left", padx=4)

        elif atype == "open_app":
            ctk.CTkLabel(
                self.value_frame, text="Path:", width=52,
                font=ctk.CTkFont(size=11),
            ).pack(side="left")
            ctk.CTkEntry(
                self.value_frame, textvariable=self.value_var,
                width=284, height=28,
                placeholder_text="C:\\...\\app.exe  or  discord  or  chrome",
            ).pack(side="left", padx=4)
            ctk.CTkButton(
                self.value_frame, text="Browse...", width=84, height=28,
                command=self._browse,
            ).pack(side="left", padx=2)

        elif atype == "send_keys":
            ctk.CTkLabel(
                self.value_frame, text="Taste(n):", width=62,
                font=ctk.CTkFont(size=11),
            ).pack(side="left")
            ctk.CTkEntry(
                self.value_frame, textvariable=self.value_var,
                width=210, height=28,
                placeholder_text="z.B.  left  /  ctrl+v  /  f5",
            ).pack(side="left", padx=4)
            self._keys_picker_var = ctk.StringVar(value="Schnellauswahl \u25bc")
            def _on_key_pick(label: str) -> None:
                v = _COMMON_LABEL_TO_V.get(label)
                if v:
                    self.value_var.set(v)
                self._keys_picker_var.set("Schnellauswahl \u25bc")
            ctk.CTkOptionMenu(
                self.value_frame,
                variable=self._keys_picker_var,
                values=_COMMON_LABELS,
                command=_on_key_pick,
                width=160, height=28,
                fg_color=("#1e2a3a", "#1e2a3a"),
                button_color=("#2a3a50", "#2a3a50"),
                button_hover_color=("#3a4a60", "#3a4a60"),
            ).pack(side="left", padx=2)
            ctk.CTkLabel(
                self.value_frame, text="  Kombinationen mit + verbinden",
                font=ctk.CTkFont(size=10),
                text_color=("#505065", "#505065"),
            ).pack(side="left")

        elif atype == "media_control":
            cur_lbl = _MEDIA_KEY_TO_LABEL.get(self.value_var.get(), _MEDIA_OPTS[0][0])
            self._media_var = ctk.StringVar(value=cur_lbl)
            ctk.CTkLabel(
                self.value_frame, text="Action:", width=52,
                font=ctk.CTkFont(size=11),
            ).pack(side="left")
            ctk.CTkOptionMenu(
                self.value_frame,
                variable=self._media_var,
                values=[lbl for lbl, _ in _MEDIA_OPTS],
                width=170, height=28,
            ).pack(side="left", padx=4)

        elif atype == "system_action":
            cur_lbl = _SYS_KEY_TO_LABEL.get(self.value_var.get(), _SYSTEM_OPTS[0][0])
            self._system_var = ctk.StringVar(value=cur_lbl)
            ctk.CTkLabel(
                self.value_frame, text="Action:", width=52,
                font=ctk.CTkFont(size=11),
            ).pack(side="left")
            ctk.CTkOptionMenu(
                self.value_frame,
                variable=self._system_var,
                values=[lbl for lbl, _ in _SYSTEM_OPTS],
                width=170, height=28,
            ).pack(side="left", padx=4)

        elif atype == "toggle_topmost":
            ctk.CTkLabel(
                self.value_frame,
                text="Toggles Always On Top for the window that was focused when the hotkey fired.",
                font=ctk.CTkFont(size=11),
                text_color=("#888899", "#888899"),
            ).pack(side="left", padx=4)

        elif atype == "toggle_stats_widget":
            ctk.CTkLabel(
                self.value_frame,
                text="Shows or hides the floating System Stats panel.",
                font=ctk.CTkFont(size=11),
                text_color=("#888899", "#888899"),
            ).pack(side="left", padx=4)

        elif atype == "show_notes_window":
            ctk.CTkLabel(
                self.value_frame,
                text="Opens the Quick Notes floating window.",
                font=ctk.CTkFont(size=11),
                text_color=("#888899", "#888899"),
            ).pack(side="left", padx=4)

        elif atype == "show_window":
            ctk.CTkLabel(
                self.value_frame,
                text="Brings the HotkeyTool main window to the front (from tray).",
                font=ctk.CTkFont(size=11),
                text_color=("#888899", "#888899"),
            ).pack(side="left", padx=4)

        elif atype == "wait":
            ctk.CTkLabel(
                self.value_frame, text="Duration (ms):", width=100,
                font=ctk.CTkFont(size=11),
            ).pack(side="left")
            ctk.CTkEntry(
                self.value_frame, textvariable=self.value_var,
                width=90, height=28,
                placeholder_text="500",
            ).pack(side="left", padx=4)
            ctk.CTkLabel(
                self.value_frame, text="  Pause before the next step.",
                font=ctk.CTkFont(size=10),
                text_color=("#505065", "#505065"),
            ).pack(side="left")

        elif atype == "color_picker":
            ctk.CTkLabel(
                self.value_frame,
                text="Samples the pixel color under the cursor and copies it as #RRGGBB.",
                font=ctk.CTkFont(size=11),
                text_color=("#888899", "#888899"),
            ).pack(side="left", padx=4)

        elif atype == "text_transform":
            ctk.CTkLabel(
                self.value_frame,
                text="Copies selected text, shows a transform picker, then pastes the result.",
                font=ctk.CTkFont(size=11),
                text_color=("#888899", "#888899"),
            ).pack(side="left", padx=4)

        elif atype == "gemini_clipboard":
            if not self.value_var.get():
                self.value_var.set(DEFAULT_PROMPT)
            ctk.CTkLabel(
                self.value_frame, text="Prompt:", width=52,
                font=ctk.CTkFont(size=11),
            ).pack(side="left")
            ctk.CTkEntry(
                self.value_frame, textvariable=self.value_var,
                width=360, height=28,
            ).pack(side="left", padx=4)

        elif atype == "gemini_ask":
            ctk.CTkLabel(
                self.value_frame,
                text="Opens a floating window to ask Gemini anything. Set API key in Settings → Gemini AI.",
                font=ctk.CTkFont(size=11),
                text_color=("#888899", "#888899"),
            ).pack(side="left", padx=4)

        elif atype == "replay_macro":
            self._refresh_macro_row()

    # ── macro helpers ─────────────────────────────────────────────────────────

    def _refresh_macro_row(self) -> None:
        """(Re-)build the value row for replay_macro type."""
        for w in self.value_frame.winfo_children():
            w.destroy()

        from utils.macro_recorder import events_count
        count = events_count(self.value_var.get())
        info_text = f"{count} events recorded" if count else "No macro recorded yet"
        info_color = ("#aaddaa", "#aaddaa") if count else ("#888899", "#888899")

        ctk.CTkLabel(
            self.value_frame, text=info_text,
            font=ctk.CTkFont(size=11),
            text_color=info_color,
            width=180, anchor="w",
        ).pack(side="left", padx=4)

        ctk.CTkButton(
            self.value_frame, text="Record", width=80, height=28,
            fg_color=("#3a1616", "#3a1616"), hover_color=("#5c2222", "#5c2222"),
            font=ctk.CTkFont(size=11),
            command=self._open_macro_recorder,
        ).pack(side="left", padx=2)

        if count:
            ctk.CTkButton(
                self.value_frame, text="Clear", width=60, height=28,
                fg_color=("#252535", "#252535"), hover_color=("#353548", "#353548"),
                font=ctk.CTkFont(size=11),
                command=self._clear_macro,
            ).pack(side="left", padx=2)

    def _open_macro_recorder(self) -> None:
        from ui.macro_record_dialog import MacroRecordDialog

        def on_done(result):
            if result:
                self.value_var.set(result)
            self._refresh_macro_row()

        MacroRecordDialog(self, on_done)

    def _clear_macro(self) -> None:
        self.value_var.set("")
        self._refresh_macro_row()

    # ── callbacks ────────────────────────────────────────────────────────────

    def _on_type_changed(self, _new_label: str) -> None:
        self.value_var.set("")
        self._build_value_row()

    def _browse(self) -> None:
        from tkinter import filedialog
        path = filedialog.askopenfilename(
            title="Select Application",
            filetypes=[("Executables", "*.exe"), ("All Files", "*.*")],
        )
        if path:
            self.value_var.set(path.replace("/", "\\"))

    # ── public ───────────────────────────────────────────────────────────────

    def get_action(self) -> Action:
        atype = _LABEL_TO_KEY.get(self.type_var.get(), "open_url")

        if atype == "media_control":
            lbl   = self._media_var.get() if self._media_var else _MEDIA_OPTS[0][0]
            value = _MEDIA_LABEL_TO_KEY.get(lbl, "play_pause")
        elif atype == "system_action":
            lbl   = self._system_var.get() if self._system_var else _SYSTEM_OPTS[0][0]
            value = _SYS_LABEL_TO_KEY.get(lbl, "lock")
        elif atype in ("toggle_topmost", "toggle_stats_widget", "show_notes_window",
                       "show_window", "color_picker", "text_transform", "gemini_ask"):
            value = ""
        else:
            value = self.value_var.get().strip()

        try:
            delay = max(0, int(self.delay_var.get()))
        except ValueError:
            delay = 0

        return Action(type=atype, value=value, delay_after_ms=delay)
