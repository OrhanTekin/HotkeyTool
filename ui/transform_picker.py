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
        grid.pack(padx=12, pady=(0, 12), fill="both", expand=True)

        for col in range(_COLS):
            grid.columnconfigure(col, weight=1)

        for i, (label, _fn) in enumerate(TRANSFORMS):
            row, col = divmod(i, _COLS)
            shortcut  = str(i + 1) if i < 9 else "  "
            btn_text  = f"[{shortcut}]  {label}"
            # Info-only transforms get a distinct colour so users know they
            # won't replace text.
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
        # Capture needed state before destroying the window
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
            # Just show the result — don't replace the user's text
            if app.window:
                app.window.after(0, lambda: _show_info_popup(app, label, result))
            return

        _write_clipboard_text(result)

        # Paste on a daemon thread — must not sleep on the main thread
        threading.Thread(
            target=_do_paste,
            args=(trigger_hwnd, label, app),
            daemon=True,
        ).start()


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
    """Small topmost popup showing a count/info result."""
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
    """Return kernel32 with correct restypes/argtypes for clipboard operations."""
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
