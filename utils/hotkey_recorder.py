"""
Temporarily hooks the keyboard to capture one key combination.
Must only be called after the main HotkeyListener is stopped,
to avoid conflicts with already-registered hotkeys.
"""
import threading

import keyboard

_CANONICAL = {
    "left ctrl": "ctrl",
    "right ctrl": "ctrl",
    "left shift": "shift",
    "right shift": "shift",
    "left alt": "alt",
    "right alt": "alt",
    "left windows": "windows",
    "right windows": "windows",
}

_MODIFIERS = {"ctrl", "shift", "alt", "windows"}


def record_hotkey(timeout: float = 8.0) -> str | None:
    """
    Block until the user presses and releases a key combination.
    Supports modifier+key combos (ctrl+f5) AND multi-key combos (f+g).
    Returns the hotkey string in keyboard-lib format, e.g. 'ctrl+shift+f3' or 'f+g'.
    Returns None on timeout or if Escape is pressed.
    """
    result: list[str | None] = [None]
    done = threading.Event()
    pressed: set[str] = set()          # all keys currently held
    non_mods_seen: set[str] = set()    # non-modifier keys seen in this gesture

    def on_event(event: keyboard.KeyboardEvent) -> None:
        name = (event.name or "").lower()
        canonical = _CANONICAL.get(name, name)

        if event.event_type == keyboard.KEY_DOWN:
            pressed.add(canonical)

            if canonical == "escape":
                done.set()
                return

            if canonical not in _MODIFIERS:
                non_mods_seen.add(canonical)

        elif event.event_type == keyboard.KEY_UP:
            # Fire on the first key-up after at least one non-modifier was held.
            # `pressed` still contains the released key here (not yet discarded),
            # so we get the full simultaneous combination.
            if non_mods_seen and canonical in non_mods_seen:
                mods = []
                if "ctrl" in pressed:
                    mods.append("ctrl")
                if "shift" in pressed:
                    mods.append("shift")
                if "alt" in pressed:
                    mods.append("alt")
                if "windows" in pressed:
                    mods.append("windows")

                non_mods = sorted(k for k in pressed if k not in _MODIFIERS)
                result[0] = "+".join(mods + non_mods)
                done.set()

            pressed.discard(canonical)
            non_mods_seen.discard(canonical)

    hook = keyboard.hook(on_event, suppress=True)
    done.wait(timeout=timeout)
    keyboard.unhook(hook)
    return result[0]
