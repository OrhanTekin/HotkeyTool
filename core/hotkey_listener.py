"""
Manages global hotkey registration using the `keyboard` library.

Threading rules
───────────────
• keyboard.add_hotkey / remove_all_hotkeys may be called from any thread,
  but we serialize all calls through _lock to make reload() atomic.
• Hotkey callbacks fire on keyboard's internal hook thread.
• Action execution is dispatched to a short-lived daemon thread so the
  hook thread is never blocked.
• on_triggered is posted back to the UI thread via root.after(); callers
  must pass a thread-safe callback.
"""
from __future__ import annotations

import ctypes
import threading
from typing import Callable, List

import keyboard

from core.action_runner import run_actions
from core.models import Binding


class HotkeyListener:
    def __init__(
        self,
        get_bindings: Callable[[], List[Binding]],
        on_triggered: Callable[[str, str], None],   # (hotkey, name)
    ) -> None:
        self._get_bindings = get_bindings
        self._on_triggered = on_triggered
        self._lock = threading.Lock()
        self._running = False

    # ── public API ───────────────────────────────────────────────────────────

    def start(self) -> None:
        with self._lock:
            if self._running:
                return
            self._register_all()
            self._running = True

    def stop(self) -> None:
        with self._lock:
            if not self._running:
                return
            try:
                keyboard.remove_all_hotkeys()
            except Exception:
                pass
            self._running = False

    def reload(self) -> None:
        """Re-register all hotkeys from the current config. Thread-safe."""
        with self._lock:
            try:
                keyboard.remove_all_hotkeys()
            except Exception:
                pass
            if self._running:
                self._register_all()

    def is_running(self) -> bool:
        return self._running

    # ── internals ────────────────────────────────────────────────────────────

    def _register_all(self) -> None:
        for binding in self._get_bindings():
            if binding.enabled and binding.hotkey:
                self._register_one(binding)

    # German → English key name aliases accepted when users type manually
    _ALIASES: dict[str, str] = {
        "strg":          "ctrl",
        "steuerung":     "ctrl",
        "umschalt":      "shift",
        "alt gr":        "alt gr",
        "altgr":         "alt gr",
        "win":           "windows",
        "super":         "windows",
        "eingabe":       "enter",
        "eingabetaste":  "enter",
        "zurück":        "backspace",
        "rücktaste":     "backspace",
        "entf":          "delete",
        "einfg":         "insert",
        "pos1":          "home",
        "ende":          "end",
        "bild auf":      "page up",
        "bild ab":       "page down",
        "druck":         "print screen",
        "esc":           "escape",
        "leer":          "space",
        "leerzeichen":   "space",
        "pfeil links":   "left",
        "pfeil rechts":  "right",
        "pfeil hoch":    "up",
        "pfeil runter":  "down",
        "links":         "left",
        "rechts":        "right",
        "hoch":          "up",
        "runter":        "down",
    }

    @staticmethod
    def normalize(hotkey: str) -> str:
        """Map German/alternative key names to keyboard-lib English names."""
        parts = [p.strip().lower() for p in hotkey.split("+")]
        mapped = [HotkeyListener._ALIASES.get(p, p) for p in parts]
        return "+".join(mapped)

    def _register_one(self, binding: Binding) -> None:
        # Capture binding by value so the lambda closes over the right object
        b = binding
        normalized = self.normalize(binding.hotkey)

        def _callback() -> None:
            self._fire(b)

        try:
            keyboard.add_hotkey(normalized, _callback, suppress=True, trigger_on_release=False)
        except Exception as exc:
            print(f"[HotkeyTool] Could not register hotkey '{normalized}': {exc}")

    def _fire(self, binding: Binding) -> None:
        # Capture foreground window NOW (keyboard hook thread) before any action
        # can change focus. Passed to run_actions for toggle_topmost.
        trigger_hwnd = ctypes.windll.user32.GetForegroundWindow()

        # Notify UI (thread-safe — callers pass root.after wrapper)
        try:
            self._on_triggered(binding.hotkey, binding.name)
        except Exception:
            pass

        # Run actions on a separate daemon thread so the hook returns fast
        t = threading.Thread(
            target=run_actions,
            args=(list(binding.actions), trigger_hwnd),
            daemon=True,
        )
        t.start()
