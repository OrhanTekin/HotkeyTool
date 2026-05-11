"""
Text snippet expander: monitors all typing via a keyboard hook and replaces
defined abbreviations with their expansion text.

Works in any app without admin rights (uses the keyboard library hook).
Character detection uses the Windows ToUnicodeEx API directly so it
handles every keyboard layout and modifier combination correctly.
The expander is paused while a macro replay or type_text action is running
to avoid recursive triggers.
"""
from __future__ import annotations

import ctypes
import sys
import threading
import time
from typing import Callable, List, TYPE_CHECKING

if TYPE_CHECKING:
    from core.models import Snippet

# ── Windows API helpers ───────────────────────────────────────────────────────

if sys.platform == "win32":
    _u32 = ctypes.windll.user32
else:
    _u32 = None  # type: ignore[assignment]

# Scan codes of keys that should reset the word buffer.
# Enter and Delete are intentionally NOT here so that a sequence like
# "@@em" → Enter → Delete → "ail" still expands as "@@email".
_RESET_SCAN_CODES: set[int] = {
    1,          # Escape
    15,         # Tab
    57,         # Space
    71,  72,  73,   # Home, Up, Page Up
    75,  77,        # Left, Right
    79,  80,  81,   # End, Down, Page Down
    82,         # Insert
    # Function keys
    59, 60, 61, 62, 63, 64, 65, 66, 67, 68, 87, 88,
}

# Scan codes of modifier keys — transparent to the buffer
_MODIFIER_SCAN_CODES: set[int] = {
    29, 157,    # Ctrl (left, right extended)
    42, 54,     # Shift (left, right)
    56, 184,    # Alt / AltGr
    91, 92, 93, # Windows / Menu
    58,         # Caps Lock
    69, 70,     # Num Lock, Scroll Lock
}

# Backspace scan code
_BACKSPACE_SC = 14


def _get_typed_char(scan_code: int) -> str:
    """
    Ask Windows what Unicode character the current key + modifier state produces.
    Uses GetKeyState (reliable in a WH_KEYBOARD_LL callback) for modifier detection
    and ToUnicodeEx for the actual character mapping.
    Returns a single character string, or "" if none / dead key / control char.
    """
    if _u32 is None:
        return ""

    # Convert scan code → virtual key (extended-key aware)
    vk = _u32.MapVirtualKeyW(scan_code, 3)   # MAPVK_VSC_TO_VK_EX = 3
    if not vk:
        return ""

    # Build a minimal keyboard-state array using GetKeyState for modifiers.
    # GetKeyState is per-message-thread; in a LL hook it reflects physical state.
    state = (ctypes.c_ubyte * 256)()
    _TOGGLE  = {0x14, 0x90, 0x91}   # CapsLock, NumLock, ScrollLock
    _PRESSED = {0x10, 0x11, 0x12}   # Shift, Ctrl, Alt
    for mod_vk in _PRESSED | _TOGGLE:
        ks = _u32.GetKeyState(mod_vk)
        if mod_vk in _TOGGLE:
            state[mod_vk] = 1 if (ks & 1) else 0
        else:
            state[mod_vk] = 0x80 if (ks & 0x8000) else 0

    buf = ctypes.create_unicode_buffer(8)
    n = _u32.ToUnicodeEx(
        vk, scan_code, state, buf, 8,
        4,                                    # flags=4 → don't update dead-key state
        _u32.GetKeyboardLayout(0),
    )
    if n != 1:
        return ""
    ch = buf.value
    # Discard ASCII control characters (but keep printable ones)
    if ord(ch) < 0x20 or ch in (" ", "\t", "\n", "\r"):
        return ""
    return ch


class SnippetExpander:
    def __init__(self, get_snippets: Callable[[], List["Snippet"]]) -> None:
        self._get_snippets = get_snippets
        self._buffer: str = ""
        self._phantom: int = 0   # skipped non-printable keys not yet consumed by Backspace
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
        self._phantom = 0

    # ── internal ─────────────────────────────────────────────────────────────

    def _on_key(self, event) -> None:
        import keyboard
        if event.event_type != keyboard.KEY_DOWN:
            return
        if self._paused:
            return

        sc = event.scan_code

        with self._lock:
            # ── Backspace: consume a phantom slot first, otherwise trim buffer ──
            if sc == _BACKSPACE_SC:
                if self._phantom > 0:
                    self._phantom -= 1
                else:
                    self._buffer = self._buffer[:-1]
                return

            # ── Modifier keys: transparent (don't touch the buffer) ──
            if sc in _MODIFIER_SCAN_CODES:
                return

            # ── Navigation / special keys: reset buffer ──
            if sc in _RESET_SCAN_CODES:
                self._buffer = ""
                self._phantom = 0
                return

            # ── Printable character: ask Windows what it is ──
            ch = _get_typed_char(sc)
            if not ch:
                # Non-printable, non-navigation key (e.g. Enter, Delete, Fn combos)
                # Count as a phantom keystroke so Backspace doesn't trim the buffer.
                self._phantom += 1
                return

            # Printable key resets the phantom counter and extends the buffer
            self._phantom = 0
            self._buffer += ch.lower()
            if len(self._buffer) > 64:
                self._buffer = self._buffer[-64:]

            # Check every enabled snippet — any of its abbreviations may match.
            buf = self._buffer
            snippets = self._get_snippets()
            for snippet in snippets:
                if not snippet.enabled:
                    continue
                for abbr_orig in snippet.abbreviations:
                    abbr = abbr_orig.lower()
                    if abbr and buf.endswith(abbr):
                        self._buffer = ""
                        threading.Thread(
                            target=self._expand,
                            args=(abbr_orig, snippet.expansion),
                            daemon=True,
                        ).start()
                        return

    def _expand(self, abbreviation: str, expansion: str) -> None:
        import keyboard
        self._paused = True
        try:
            time.sleep(0.06)  # let the last keystroke settle
            for _ in abbreviation:
                keyboard.press_and_release("backspace")
                time.sleep(0.02)
            keyboard.write(expansion, delay=0.02)
        finally:
            self._paused = False
            with self._lock:
                self._buffer = ""
