"""
Records keyboard and mouse-click events with timing for macro playback.

record_macro() — blocks until stop_event is set or timeout, returns JSON string.
replay_macro() — replays the JSON string with original timing.
"""
from __future__ import annotations

import json
import threading
import time
from typing import Optional


def record_macro(
    stop_event: threading.Event,
    timeout: float = 120.0,
    trim_last_click: list[bool] | None = None,
) -> Optional[str]:
    """
    Record keyboard key presses and mouse clicks.

    stop_event  : set this from outside (e.g. Stop button) to finish recording.
    trim_last_click : mutable [bool] flag; if True after stop, the last mouse
                      click is removed (used to exclude the Stop-button click).
    Returns a JSON string of events, or None if nothing was recorded.
    """
    import keyboard

    events: list[dict] = []
    t_last: list[float] = [time.monotonic()]
    _held_keys: set[str] = set()

    def dt_ms() -> int:
        now = time.monotonic()
        ms = int((now - t_last[0]) * 1000)
        t_last[0] = now
        return ms

    def on_key(event: keyboard.KeyboardEvent) -> None:
        name = (event.name or "").lower()
        if name == "escape":
            return  # Escape is handled by the dedicated hook below
        if stop_event.is_set():
            return
        if event.event_type == keyboard.KEY_DOWN:
            if name in _held_keys:
                return  # Skip auto-repeat
            _held_keys.add(name)
            events.append({"t": "kd", "k": event.name, "dt": dt_ms()})
        else:
            _held_keys.discard(name)
            events.append({"t": "ku", "k": event.name, "dt": dt_ms()})

    # Escape: separate suppress=True hook so it doesn't reach other apps
    def _escape_stop():
        stop_event.set()

    keyboard.add_hotkey("escape", _escape_stop, suppress=True)

    # General recording hook (not suppressed — keys still reach the active app)
    kb_hook = keyboard.hook(on_key, suppress=False)

    # Optional mouse click recording
    mouse_hook = None
    try:
        import mouse as _mouse

        def on_mouse(event) -> None:
            import mouse as m
            if stop_event.is_set():
                return
            if isinstance(event, m.ButtonEvent) and event.event_type == m.DOWN:
                x, y = m.get_position()
                events.append({
                    "t": "mc",
                    "b": event.button,
                    "x": x,
                    "y": y,
                    "dt": dt_ms(),
                })

        mouse_hook = _mouse.hook(on_mouse)
    except Exception:
        pass

    stop_event.wait(timeout=timeout)

    # Clean up hooks
    keyboard.unhook(kb_hook)
    try:
        keyboard.remove_hotkey("escape")
    except Exception:
        pass
    if mouse_hook is not None:
        try:
            import mouse as _mouse
            _mouse.unhook(mouse_hook)
        except Exception:
            pass

    # Remove the Stop-button click if requested
    if trim_last_click and trim_last_click[0]:
        for i in range(len(events) - 1, -1, -1):
            if events[i].get("t") == "mc":
                events.pop(i)
                break

    return json.dumps(events) if events else None


def replay_macro(events_json: str) -> None:
    """Replay a macro from its JSON representation."""
    import ctypes
    import keyboard

    try:
        events = json.loads(events_json)
    except Exception:
        return

    user32 = ctypes.windll.user32
    _MOUSEEVENTF_LEFTDOWN  = 0x0002
    _MOUSEEVENTF_LEFTUP    = 0x0004
    _MOUSEEVENTF_RIGHTDOWN = 0x0008
    _MOUSEEVENTF_RIGHTUP   = 0x0010

    _btn_dn = {"left": _MOUSEEVENTF_LEFTDOWN,  "right": _MOUSEEVENTF_RIGHTDOWN}
    _btn_up = {"left": _MOUSEEVENTF_LEFTUP,    "right": _MOUSEEVENTF_RIGHTUP}

    for event in events:
        dt = event.get("dt", 0)
        if dt > 0:
            time.sleep(dt / 1000.0)

        t = event.get("t")
        if t == "kd":
            try:
                keyboard.press(event["k"])
            except Exception:
                pass
        elif t == "ku":
            try:
                keyboard.release(event["k"])
            except Exception:
                pass
        elif t == "mc":
            x, y = event.get("x", 0), event.get("y", 0)
            btn  = event.get("b", "left")
            user32.SetCursorPos(x, y)
            time.sleep(0.02)
            if btn in _btn_dn:
                user32.mouse_event(_btn_dn[btn], x, y, 0, 0)
                time.sleep(0.05)
                user32.mouse_event(_btn_up[btn], x, y, 0, 0)


def events_count(events_json: str) -> int:
    """Return the number of meaningful recorded events (key-downs + mouse clicks)."""
    try:
        return sum(1 for e in json.loads(events_json) if e.get("t") in ("kd", "mc"))
    except Exception:
        return 0
