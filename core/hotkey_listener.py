"""
Manages global hotkey registration.

Dispatch via a single `keyboard.hook(suppress=True)` plus direct queries
to Windows' `GetAsyncKeyState` at the trigger-key moment.  We do NOT track
modifier state from events — Windows' AltGr emulation on EU layouts can
swallow or rewrite events in ways that leave event-based tracking out of
sync.  `GetAsyncKeyState` returns the actual physical state of every key
regardless of how the OS-level layout layer rewrote the event stream, so
it's the only consistent answer to "is Ctrl really held right now".

Threading rules
───────────────
• keyboard.hook may be called from any thread, but we serialize public
  start/stop/reload through _lock.
• Hook callback fires on keyboard's internal hook thread.
• Action execution is dispatched to a daemon thread so the hook returns
  fast.
• on_triggered is posted back to the UI thread via root.after() — callers
  must pass a thread-safe callback.
"""
from __future__ import annotations

import ctypes
import threading
from typing import Callable, Dict, FrozenSet, List, Tuple

import keyboard

from core.action_runner import run_actions
from core.models import Binding


_MODIFIERS = {"ctrl", "alt", "shift", "windows", "alt gr"}

# Windows VK codes — used by GetAsyncKeyState to read live key state.
_VK_CONTROL = 0x11   # either left or right Ctrl
_VK_MENU    = 0x12   # either left or right Alt
_VK_SHIFT   = 0x10   # either left or right Shift
_VK_LWIN    = 0x5B
_VK_RWIN    = 0x5C

# Names that the keyboard library emits for the trigger key (e.g. "x", "f5").
# Modifier names ("ctrl", "left ctrl", etc.) are caught by a separate check
# so we never accidentally treat them as triggers.
_MODIFIER_EVENT_NAMES = {
    "ctrl", "left ctrl", "right ctrl",
    "alt", "left alt", "right alt",
    "shift", "left shift", "right shift",
    "windows", "left windows", "right windows",
    "alt gr",
}


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

        # Index: trigger_name -> [(required_modifier_set, binding), ...]
        self._index: Dict[str, List[Tuple[FrozenSet[str], Binding]]] = {}
        self._hook_handle = None
        self._user32 = ctypes.windll.user32

    # ── public API ───────────────────────────────────────────────────────────

    def start(self) -> None:
        with self._lock:
            if self._running:
                return
            self._build_index()
            self._install_hook()
            self._running = True

    def stop(self) -> None:
        with self._lock:
            if not self._running:
                return
            self._uninstall_hook()
            self._index = {}
            self._running = False

    def reload(self) -> None:
        with self._lock:
            self._build_index()
            # No need to reinstall the hook — same callback, fresh index.

    def is_running(self) -> bool:
        return self._running

    # ── normalization (German / alt-name aliases) ────────────────────────────

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
        parts = [p.strip().lower() for p in hotkey.split("+")]
        mapped = [HotkeyListener._ALIASES.get(p, p) for p in parts]
        return "+".join(mapped)

    # ── index ────────────────────────────────────────────────────────────────

    def _build_index(self) -> None:
        new_index: Dict[str, List[Tuple[FrozenSet[str], Binding]]] = {}
        for binding in self._get_bindings():
            if not binding.enabled or not binding.hotkey:
                continue
            normalized = self.normalize(binding.hotkey)
            parts = [p.strip() for p in normalized.split("+") if p.strip()]
            if not parts:
                continue
            mods = frozenset(p for p in parts if p in _MODIFIERS)
            triggers = [p for p in parts if p not in _MODIFIERS]
            if len(triggers) != 1:
                # We only support single-trigger hotkeys (the format actually
                # used everywhere in the app).  Multi-trigger / chord hotkeys
                # would need a different matcher.
                continue
            new_index.setdefault(triggers[0], []).append((mods, binding))
        # Atomic swap — the hook thread may be reading _index concurrently.
        self._index = new_index

    # ── hook ─────────────────────────────────────────────────────────────────

    def _install_hook(self) -> None:
        # suppress=True so we can block matched events from reaching apps.
        # The single hook covers every binding — no per-hotkey registration.
        self._hook_handle = keyboard.hook(self._on_event, suppress=True)

    def _uninstall_hook(self) -> None:
        if self._hook_handle is not None:
            try:
                keyboard.unhook(self._hook_handle)
            except Exception:
                pass
            self._hook_handle = None

    def _current_modifiers(self) -> set:
        """Read live physical key state from Windows.

        GetAsyncKeyState is the source of truth: when AltGr emulation is
        active on EU layouts, the OS still reports VK_CONTROL/VK_MENU as
        pressed even though the corresponding L-Alt event may have been
        swallowed.  This sidesteps every event-based pitfall.
        """
        u32 = self._user32
        mods: set = set()
        if u32.GetAsyncKeyState(_VK_CONTROL) & 0x8000:
            mods.add("ctrl")
        if u32.GetAsyncKeyState(_VK_MENU)    & 0x8000:
            mods.add("alt")
        if u32.GetAsyncKeyState(_VK_SHIFT)   & 0x8000:
            mods.add("shift")
        if (u32.GetAsyncKeyState(_VK_LWIN) & 0x8000) \
                or (u32.GetAsyncKeyState(_VK_RWIN) & 0x8000):
            mods.add("windows")
        return mods

    def _on_event(self, event) -> bool:
        """Return False to suppress the event (match), True to let it pass."""
        if event.event_type != keyboard.KEY_DOWN:
            return True

        name = (event.name or "").lower()
        if not name or name in _MODIFIER_EVENT_NAMES:
            return True

        candidates = self._index.get(name, [])
        if not candidates:
            return True

        effective = self._current_modifiers()
        for required, binding in candidates:
            # Treat "alt gr" as ctrl+alt (a binding written either way matches
            # the same physical Ctrl+Alt state).
            req_effective = set(required)
            if "alt gr" in req_effective:
                req_effective.discard("alt gr")
                req_effective.add("ctrl")
                req_effective.add("alt")
            if req_effective == effective:
                self._fire(binding)
                return False  # suppress so the trigger key isn't typed
        return True

    # ── action dispatch ──────────────────────────────────────────────────────

    def _fire(self, binding: Binding) -> None:
        # Capture foreground window NOW (still on the hook thread) before any
        # action can change focus.  Passed to run_actions for toggle_topmost.
        trigger_hwnd = ctypes.windll.user32.GetForegroundWindow()

        try:
            self._on_triggered(binding.hotkey, binding.name)
        except Exception:
            pass

        # Run actions on a daemon thread so the hook returns fast.
        t = threading.Thread(
            target=run_actions,
            args=(list(binding.actions), trigger_hwnd),
            daemon=True,
        )
        t.start()
