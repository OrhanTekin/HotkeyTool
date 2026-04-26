"""
Floating picker shown when a 'text_transform' action fires.

Flow:
  1. Before this window is created, the action_runner thread already sent
     Ctrl+C and waited ~200 ms, so the clipboard holds the selected text.
  2. User clicks a transform option (or presses 1-9 / Escape).
  3. Picker reads the clipboard, applies the transform, writes it back,
     then restores focus to trigger_hwnd and sends Ctrl+V on a daemon thread
     (so the main thread is never blocked).
  4. "Count: chars & words" is INFO_ONLY: a small result popup appears instead
     of replacing the selected text.
"""
from __future__ import annotations

import ctypes
import threading
import time
from typing import TYPE_CHECKING

import customtkinter as ctk

from core.text_transforms import INFO_ONLY_TRANSFORMS, TRANSFORMS

if TYPE_CHECKING:
    from app import App

_COLS = 2   # buttons per row


class TransformPicker(ctk.CTkToplevel):
    def __init__(self, app: "App", trigger_hwnd: int) -> None:
        super().__init__()
        self.app = app
        self._trigger_hwnd = trigger_hwnd

        self.title("Transform Text")
        self.resizable(False, False)
        self.attributes("-topmost", True)

        self._build()
        self._center()

        self.protocol("WM_DELETE_WINDOW", self.destroy)
        self.bind("<Escape>", lambda _e: self.destroy())

        # Number keys 1–9 for the first 9 options
        for i in range(min(9, len(TRANSFORMS))):
            self.bind(str(i + 1), lambda _e, idx=i: self._apply(idx))

        self.lift()
        self.after(60, self.focus_force)

    # ── layout ────────────────────────────────────────────────────────────────

    def _build(self) -> None:
        ctk.CTkLabel(
            self,
            text="Transform Text  —  choose an option or press Esc to cancel",
            font=ctk.CTkFont(size=12),
            text_color=("#7788aa", "#7788aa"),
        ).pack(padx=16, pady=(12, 6))

        grid = ctk.CTkFrame(self, fg_color="transparent")
        grid.pack(padx=12, pady=(0, 4), fill="both", expand=True)

        for col in range(_COLS):
            grid.columnconfigure(col, weight=1)

        for i, (label, _fn) in enumerate(TRANSFORMS):
            row, col = divmod(i, _COLS)
            shortcut  = str(i + 1) if i < 9 else "  "
            btn_text  = f"[{shortcut}]  {label}"
            is_info = label in INFO_ONLY_TRANSFORMS
            fg   = ("#1e2a1e", "#1e2a1e") if is_info else ("#1a1a2e", "#1a1a2e")
            hov  = ("#2a3a2a", "#2a3a2a") if is_info else ("#2a2a50", "#2a2a50")

            ctk.CTkButton(
                grid,
                text=btn_text,
                anchor="w",
                width=210, height=30,
                font=ctk.CTkFont(size=12),
                fg_color=fg,
                hover_color=hov,
                text_color=("#d0d0ee", "#d0d0ee"),
                command=lambda idx=i: self._apply(idx),
            ).grid(row=row, column=col, padx=3, pady=2, sticky="ew")

        # Separator + Reformat button
        ctk.CTkFrame(
            self, height=1, fg_color=("#2a2a44", "#2a2a44"),
        ).pack(fill="x", padx=12, pady=(6, 4))

        ctk.CTkButton(
            self,
            text="{ }   Reformat Code  (AI)...",
            anchor="w",
            height=32,
            font=ctk.CTkFont(size=12),
            fg_color=("#0e2018", "#0e2018"),
            hover_color=("#1a3224", "#1a3224"),
            text_color=("#77bb99", "#77bb99"),
            command=self._open_format_picker,
        ).pack(padx=12, pady=(0, 12), fill="x")

    def _center(self) -> None:
        self.update_idletasks()
        w  = self.winfo_reqwidth()
        h  = self.winfo_reqheight()
        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()
        self.geometry(f"+{(sw - w) // 2}+{(sh - h) // 2}")

    # ── transform logic ───────────────────────────────────────────────────────

    def _apply(self, index: int) -> None:
        label, fn = TRANSFORMS[index]
        trigger_hwnd = self._trigger_hwnd
        app          = self.app
        self.destroy()

        text = _read_clipboard_text()
        if not text:
            return

        try:
            result = fn(text)
        except Exception as exc:
            print(f"[HotkeyTool] Transform '{label}' failed: {exc}")
            return

        if label in INFO_ONLY_TRANSFORMS:
            if app.window:
                app.window.after(0, lambda: _show_info_popup(app, label, result))
            return

        _write_clipboard_text(result)

        threading.Thread(
            target=_do_paste,
            args=(trigger_hwnd, label, app),
            daemon=True,
        ).start()

    def _open_format_picker(self) -> None:
        trigger_hwnd = self._trigger_hwnd
        app          = self.app
        self.destroy()
        if app.window:
            app.window.after(0, lambda: FormatPicker(app, trigger_hwnd))


# ── format picker ─────────────────────────────────────────────────────────────

_FORMAT_COLS = 3

_FORMAT_GROUPS: list[tuple[str, str, str, list[tuple[str, str]]]] = [
    (
        "Web",
        "#0d1e2e", "#1a3248",
        [
            ("HTML",       "html",       "HTML"),
            ("CSS",        "css",        "CSS"),
            ("JavaScript", "javascript", "JavaScript"),
            ("TypeScript", "typescript", "TypeScript"),
            ("PHP",        "php",        "PHP"),
        ],
    ),
    (
        "Languages",
        "#14102a", "#241e44",
        [
            ("Python",  "python",  "Python"),
            ("Java",    "java",    "Java"),
            ("C#",      "csharp",  "C#"),
            ("Ruby",    "ruby",    "Ruby"),
            ("Swift",   "swift",   "Swift"),
            ("Kotlin",  "kotlin",  "Kotlin"),
            ("R",       "r",       "R"),
        ],
    ),
    (
        "Systems",
        "#180e1e", "#281e30",
        [
            ("C",    "c",    "C"),
            ("C++",  "cpp",  "C++"),
            ("Go",   "go",   "Go"),
            ("Rust", "rust", "Rust"),
        ],
    ),
    (
        "Data / Config",
        "#0d1c1c", "#1a2e2e",
        [
            ("JSON",     "json",     "JSON"),
            ("XML",      "xml",      "XML"),
            ("YAML",     "yaml",     "YAML"),
            ("SQL",      "sql",      "SQL"),
            ("Markdown", "markdown", "Markdown"),
        ],
    ),
    (
        "Shell / DevOps",
        "#0d1c14", "#1a2e20",
        [
            ("Bash",        "bash",        "Bash"),
            ("PowerShell",  "powershell",  "PowerShell"),
            ("Dockerfile",  "dockerfile",  "Dockerfile"),
        ],
    ),
]


class FormatPicker(ctk.CTkToplevel):
    def __init__(self, app: "App", trigger_hwnd: int) -> None:
        super().__init__()
        self.app = app
        self._trigger_hwnd = trigger_hwnd

        self.title("Reformat Code")
        self.resizable(False, False)
        self.attributes("-topmost", True)

        self._build()
        self._center()

        self.protocol("WM_DELETE_WINDOW", self.destroy)
        self.bind("<Escape>", lambda _e: self.destroy())

        self.lift()
        self.after(60, self.focus_force)

    def _build(self) -> None:
        ctk.CTkLabel(
            self,
            text="Fix indentation, spacing & syntax  •  Powered by Gemini AI",
            font=ctk.CTkFont(size=12),
            text_color=("#7788aa", "#7788aa"),
        ).pack(padx=16, pady=(12, 8))

        scroll = ctk.CTkScrollableFrame(
            self, fg_color="transparent",
            width=500, height=460,
        )
        scroll.pack(padx=12, pady=(0, 4), fill="both", expand=True)

        for group_name, fg, hov, langs in _FORMAT_GROUPS:
            # Section header with horizontal rule
            hdr = ctk.CTkFrame(scroll, fg_color="transparent")
            hdr.pack(fill="x", pady=(8, 2))
            ctk.CTkLabel(
                hdr, text=group_name,
                font=ctk.CTkFont(size=10, weight="bold"),
                text_color=("#5588aa", "#5588aa"),
                anchor="w",
            ).pack(side="left")
            ctk.CTkFrame(
                hdr, height=1, fg_color=("#2a3040", "#2a3040"),
            ).pack(side="left", fill="x", expand=True, padx=(8, 0), pady=6)

            # Button grid
            row_frame: ctk.CTkFrame | None = None
            for i, (label, lang_id, lang_name) in enumerate(langs):
                if i % _FORMAT_COLS == 0:
                    row_frame = ctk.CTkFrame(scroll, fg_color="transparent")
                    row_frame.pack(fill="x", pady=1)
                    for c in range(_FORMAT_COLS):
                        row_frame.columnconfigure(c, weight=1)

                ctk.CTkButton(
                    row_frame,
                    text=label,
                    height=30,
                    font=ctk.CTkFont(size=12),
                    fg_color=(fg, fg),
                    hover_color=(hov, hov),
                    text_color=("#d0d8ee", "#d0d8ee"),
                    command=lambda lid=lang_id, lname=lang_name: self._apply(lid, lname),
                ).grid(
                    row=0,
                    column=i % _FORMAT_COLS,
                    padx=2, pady=0,
                    sticky="ew",
                )

        # Plain Text at the bottom
        ctk.CTkFrame(
            scroll, height=1, fg_color=("#2a2a44", "#2a2a44"),
        ).pack(fill="x", pady=(10, 6))

        ctk.CTkButton(
            scroll,
            text="Plain Text  (clean up whitespace & structure)",
            height=30,
            font=ctk.CTkFont(size=12),
            fg_color=("#222230", "#222230"),
            hover_color=("#323244", "#323244"),
            text_color=("#9999bb", "#9999bb"),
            command=lambda: self._apply("", "Plain Text"),
        ).pack(fill="x", pady=(0, 8))

    def _center(self) -> None:
        self.update_idletasks()
        w  = self.winfo_reqwidth()
        h  = self.winfo_reqheight()
        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()
        self.geometry(f"+{(sw - w) // 2}+{(sh - h) // 2}")

    def _apply(self, lang_id: str, lang_name: str) -> None:
        trigger_hwnd = self._trigger_hwnd
        app          = self.app
        self.destroy()

        text = _read_clipboard_text()
        if not text:
            return

        key = app.config.settings.gemini_api_key.strip()
        if not key:
            if app.window:
                app.window.after(0, lambda: app.window.update_status(
                    "Reformat Code: no Gemini API key — add one in Settings -> Gemini AI"))
            return

        if app.window:
            app.window.after(0, lambda: app.window.update_status(
                f"Reformatting {lang_name} code via Gemini..."))

        threading.Thread(
            target=_reformat_with_gemini,
            args=(key, lang_name, text, trigger_hwnd, app),
            daemon=True,
        ).start()


# ── Gemini reformat worker ────────────────────────────────────────────────────

def _reformat_with_gemini(key: str, lang_name: str, text: str,
                           trigger_hwnd: int, app) -> None:
    from core.gemini import call_gemini

    if lang_name == "Plain Text":
        prompt = (
            "Clean up the formatting of the following text. "
            "Normalize paragraph spacing, fix inconsistent indentation, "
            "and tidy up the structure. "
            "Output ONLY the cleaned text — no explanations."
        )
    elif lang_name == "SQL":
        prompt = (
            "Reformat the following SQL to follow standard conventions: "
            "uppercase keywords (SELECT, FROM, WHERE, JOIN, etc.), "
            "consistent indentation with 4 spaces, one clause per line. "
            "Output ONLY the formatted SQL — no explanations, no markdown fences."
        )
    elif lang_name == "JSON":
        prompt = (
            "Reformat the following JSON with 2-space indentation and proper structure. "
            "Output ONLY the formatted JSON — no explanations, no markdown fences."
        )
    else:
        prompt = (
            f"Reformat the following {lang_name} code to follow standard conventions. "
            f"Fix indentation (consistent spaces), spacing, and obvious syntax issues. "
            f"Apply the standard {lang_name} style guide where applicable. "
            f"Output ONLY the corrected code — no explanations, no markdown fences."
        )

    try:
        result = call_gemini(key, f"{prompt}\n\n{text}")
        result = _strip_code_fence(result)
    except Exception as exc:
        if app.window:
            app.window.after(0, lambda e=str(exc): app.window.update_status(
                f"Reformat failed: {e}"))
        return

    _write_clipboard_text(result)
    _do_paste(trigger_hwnd, f"Reformat: {lang_name}", app)


def _strip_code_fence(text: str) -> str:
    """Remove markdown code fences Gemini sometimes adds despite being told not to."""
    text = text.strip()
    lines = text.splitlines()
    if lines and lines[0].startswith("```"):
        lines = lines[1:]
    if lines and lines[-1].strip() == "```":
        lines = lines[:-1]
    return "\n".join(lines)


# ── paste worker (daemon thread) ─────────────────────────────────────────────

def _do_paste(trigger_hwnd: int, label: str, app) -> None:
    try:
        if trigger_hwnd:
            ctypes.windll.user32.SetForegroundWindow(trigger_hwnd)
            time.sleep(0.10)
        import keyboard
        keyboard.send("ctrl+v")
    except Exception:
        pass
    if app.window:
        app.window.after(0, lambda: app.window.update_status(f"Transformed: {label}"))


# ── info popup ────────────────────────────────────────────────────────────────

def _show_info_popup(app, label: str, result: str) -> None:
    win = ctk.CTkToplevel()
    win.title(label)
    win.resizable(False, False)
    win.attributes("-topmost", True)

    ctk.CTkLabel(
        win, text=result,
        font=ctk.CTkFont(size=14, weight="bold"),
        text_color=("#aaddaa", "#aaddaa"),
    ).pack(padx=28, pady=(20, 8))

    ctk.CTkButton(
        win, text="OK", width=80,
        command=win.destroy,
    ).pack(pady=(4, 16))

    win.update_idletasks()
    w, h = win.winfo_reqwidth(), win.winfo_reqheight()
    sw, sh = win.winfo_screenwidth(), win.winfo_screenheight()
    win.geometry(f"+{(sw - w) // 2}+{(sh - h) // 2}")
    win.lift()
    win.after(60, win.focus_force)

    if app.window:
        app.window.update_status(f"{label}: {result}")


# ── clipboard helpers (usable from any thread) ────────────────────────────────

def _clipboard_kernel32():
    k32 = ctypes.windll.kernel32
    k32.GlobalAlloc.restype   = ctypes.c_void_p
    k32.GlobalAlloc.argtypes  = [ctypes.c_uint, ctypes.c_size_t]
    k32.GlobalLock.restype    = ctypes.c_void_p
    k32.GlobalLock.argtypes   = [ctypes.c_void_p]
    k32.GlobalUnlock.argtypes = [ctypes.c_void_p]
    k32.GlobalFree.argtypes   = [ctypes.c_void_p]
    return k32


def _read_clipboard_text() -> str:
    CF_UNICODETEXT = 13
    user32   = ctypes.windll.user32
    kernel32 = _clipboard_kernel32()
    user32.GetClipboardData.restype = ctypes.c_void_p
    if not user32.OpenClipboard(None):
        return ""
    try:
        h = user32.GetClipboardData(CF_UNICODETEXT)
        if not h:
            return ""
        p = kernel32.GlobalLock(h)
        if not p:
            return ""
        try:
            return ctypes.wstring_at(p)
        finally:
            kernel32.GlobalUnlock(h)
    finally:
        user32.CloseClipboard()


def _write_clipboard_text(text: str) -> None:
    CF_UNICODETEXT = 13
    GMEM_MOVEABLE  = 0x0002
    user32   = ctypes.windll.user32
    kernel32 = _clipboard_kernel32()
    encoded  = (text + "\0").encode("utf-16-le")
    h = kernel32.GlobalAlloc(GMEM_MOVEABLE, len(encoded))
    if not h:
        return
    p = kernel32.GlobalLock(h)
    if not p:
        kernel32.GlobalFree(h)
        return
    ctypes.memmove(p, encoded, len(encoded))
    kernel32.GlobalUnlock(h)
    if user32.OpenClipboard(None):
        user32.EmptyClipboard()
        user32.SetClipboardData(CF_UNICODETEXT, ctypes.c_void_p(h))
        user32.CloseClipboard()
