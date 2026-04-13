"""
Text snippet expander: monitors all typing via a keyboard hook and replaces
defined abbreviations with their expansion text.

Works in any app without admin rights (uses the keyboard library hook).
The expander is paused while a macro replay or type_text action is running
to avoid recursive triggers.
"""
from __future__ import annotations

import threading
import time
from typing import Callable, List, TYPE_CHECKING

if TYPE_CHECKING:
    from core.models import Snippet

# Characters that reset the current-word buffer (tab is handled separately)
_RESET_CHARS = {
    "space", "enter", "escape",
    "backspace", "delete",
    "left", "right", "up", "down",
    "home", "end", "page up", "page down",
}


class SnippetExpander:
    def __init__(self, get_snippets: Callable[[], List["Snippet"]]) -> None:
        self._get_snippets = get_snippets
        self._buffer: str = ""
        self._hook = None
        self._lock = threading.Lock()
        self._paused = False

    def start(self) -> None:
        import keyboard
        self._hook = keyboard.hook(self._on_key, suppress=False)

    def stop(self) -> None:
        if self._hook is not None:
            import keyboard
            try:
                keyboard.unhook(self._hook)
            except Exception:
                pass
            self._hook = None

    def pause(self) -> None:
        """Pause expansion (e.g. while replaying a macro or type_text action)."""
        self._paused = True

    def resume(self) -> None:
        self._paused = False
        self._buffer = ""

    # ── internal ─────────────────────────────────────────────────────────────

    def _on_key(self, event) -> None:
        import keyboard
        if event.event_type != keyboard.KEY_DOWN:
            return
        if self._paused:
            return

        name = (event.name or "").lower()

        with self._lock:
            if name == "backspace":
                self._buffer = self._buffer[:-1]
                return

            if name in _RESET_CHARS or len(name) > 1:
                # Multi-char key names (ctrl, shift, f5, …) reset the buffer
                # single printable chars (a-z, 0-9, symbols) have len == 1
                self._buffer = ""
                return

            if name == "tab":
                # Tab is the expansion trigger: check for a matching snippet
                buf = self._buffer
                self._buffer = ""
                snippets = self._get_snippets()
                for snippet in snippets:
                    if not snippet.enabled:
                        continue
                    abbr = snippet.abbreviation
                    if abbr and buf.endswith(abbr):
                        # Expand: erase abbreviation + the Tab, type expansion
                        threading.Thread(
                            target=self._expand,
                            args=(abbr, snippet.expansion, True),
                            daemon=True,
                        ).start()
                        return
                # No match — Tab was already sent to the app, nothing to do
                return

            # Single printable character
            self._buffer += name
            # Keep buffer bounded
            if len(self._buffer) > 64:
                self._buffer = self._buffer[-64:]

    def _expand(self, abbreviation: str, expansion: str, erase_trigger: bool = False) -> None:
        import keyboard
        self._paused = True
        try:
            time.sleep(0.05)  # brief pause so the last typed char settles
            # Erase the abbreviation + optional trigger char (Tab)
            chars_to_erase = len(abbreviation) + (1 if erase_trigger else 0)
            for _ in range(chars_to_erase):
                keyboard.press_and_release("backspace")
                time.sleep(0.02)
            # Type the expansion
            keyboard.write(expansion, delay=0.02)
        finally:
            self._paused = False
            with self._lock:
                self._buffer = ""
