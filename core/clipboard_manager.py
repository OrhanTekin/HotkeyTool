"""
Clipboard manager — history store only.

Clipboard *reading* and *writing* are both done on the main (Tkinter) thread
via ClipboardTab, which uses tkinter's clipboard_get() / clipboard_clear() /
clipboard_append().  This avoids the delayed-rendering problem: modern apps
(Chrome, Edge, VS Code …) only fill the clipboard when they receive a
WM_RENDERFORMAT message, which requires a message queue.  Tkinter's main
thread has one; a daemon thread does not.
"""
from __future__ import annotations

from typing import Callable, List


MAX_ITEMS = 20


class ClipboardManager:
    """
    Pure in-memory history store.  No threads — the caller (ClipboardTab) is
    responsible for detecting clipboard changes and calling add().
    """

    def __init__(self) -> None:
        self._history: List[str] = []
        self._on_change: Callable[[List[str]], None] | None = None

    def set_callback(self, fn: Callable[[List[str]], None] | None) -> None:
        self._on_change = fn

    # start/stop are no-ops kept for API compatibility with app.py
    def start(self) -> None:
        pass

    def stop(self) -> None:
        pass

    @property
    def history(self) -> List[str]:
        return list(self._history)

    def add(self, text: str) -> None:
        """Add a text entry (called from the main thread by ClipboardTab)."""
        if not text or not text.strip():
            return
        if self._history and self._history[0] == text:
            return
        if text in self._history:
            self._history.remove(text)
        self._history.insert(0, text)
        if len(self._history) > MAX_ITEMS:
            self._history = self._history[:MAX_ITEMS]
        if self._on_change:
            self._on_change(list(self._history))

    def copy_item(self, text: str) -> None:
        """Move text to top of history (caller is responsible for writing to clipboard)."""
        if text in self._history:
            self._history.remove(text)
        self._history.insert(0, text)
        if self._on_change:
            self._on_change(list(self._history))

    def clear_history(self) -> None:
        self._history.clear()
        if self._on_change:
            self._on_change([])
