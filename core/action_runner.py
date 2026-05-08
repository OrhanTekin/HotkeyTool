"""
Executes Action objects. Runs on a dedicated action thread — never touches the UI.
"""
import ctypes
import os
import subprocess
import time
import webbrowser
from typing import Callable, Dict, List

from core.models import Action

# ── app-level callback registry ──────────────────────────────────────────────
# Actions that need to reach UI/app-level services (stats, notes, …) register
# here. app.py calls register_app_callback() after creating the services.

_app_callbacks: Dict[str, Callable] = {}

def register_app_callback(name: str, fn: Callable) -> None:
    _app_callbacks[name] = fn

# Windows Virtual-Key codes for media / volume
_VK = {
    "next_track":   0xB0,
    "prev_track":   0xB1,
    "stop":         0xB2,
    "play_pause":   0xB3,
    "mute":         0xAD,
    "volume_down":  0xAE,
    "volume_up":    0xAF,
}

_KEYEVENTF_EXTENDEDKEY = 0x0001
_KEYEVENTF_KEYUP       = 0x0002

# SetWindowPos flags / insert-after handles
_HWND_TOPMOST   = -1
_HWND_NOTOPMOST = -2
_SWP_NOMOVE     = 0x0002
_SWP_NOSIZE     = 0x0001
_GWL_EXSTYLE    = -20
_WS_EX_TOPMOST  = 0x0008


def _send_vk(vk: int) -> None:
    """Send a virtual key press via keybd_event."""
    user32 = ctypes.windll.user32
    user32.keybd_event(vk, 0, _KEYEVENTF_EXTENDEDKEY, 0)
    time.sleep(0.02)
    user32.keybd_event(vk, 0, _KEYEVENTF_EXTENDEDKEY | _KEYEVENTF_KEYUP, 0)


# ── public ──────────────────────────────────────────────────────────────────

def run_actions(actions: List[Action], trigger_hwnd: int = 0) -> None:
    """Execute a list of actions sequentially. Called from a daemon thread.

    trigger_hwnd: foreground window handle captured at the moment the hotkey
    fired; used by toggle_topmost so it acts on the right window even if focus
    has shifted by the time the action runs.
    """
    if not trigger_hwnd:
        trigger_hwnd = ctypes.windll.user32.GetForegroundWindow()

    for action in actions:
        try:
            _dispatch(action, trigger_hwnd)
        except Exception as exc:
            print(f"[HotkeyTool] Action error ({action.type}={action.value}): {exc}")
        if action.delay_after_ms > 0:
            time.sleep(action.delay_after_ms / 1000.0)


# ── dispatcher ───────────────────────────────────────────────────────────────

def _dispatch(action: Action, trigger_hwnd: int = 0) -> None:
    if action.type == "toggle_topmost":
        _toggle_topmost(trigger_hwnd)
        return
    if action.type == "replay_macro":
        _replay_macro(action)
        return
    if action.type in ("toggle_stats_widget", "show_notes_window", "show_window"):
        fn = _app_callbacks.get(action.type)
        if fn:
            fn()
        return

    if action.type == "text_transform":
        _text_transform(action, trigger_hwnd)
        return

    if action.type == "gemini_clipboard":
        _gemini_clipboard(action)
        return

    if action.type == "gemini_ask":
        fn = _app_callbacks.get("gemini_ask")
        if fn:
            fn()
        return

    if action.type == "show_transform_picker":
        fn = _app_callbacks.get("show_transform_picker")
        if fn:
            fn(trigger_hwnd)
        return

    handlers = {
        "open_url":      _open_url,
        "open_app":      _open_app,
        "type_text":     _type_text,
        "run_command":   _run_command,
        "media_control": _media_control,
        "send_keys":     _send_keys,
        "wait":          _wait,
        "color_picker":  _color_picker,
    }
    fn = handlers.get(action.type)
    if fn:
        fn(action)


# ── action handlers ──────────────────────────────────────────────────────────

def _open_url(action: Action) -> None:
    webbrowser.open(action.value)


def _open_app(action: Action) -> None:
    value = action.value.strip()
    args  = action.args.strip()
    if not value:
        return
    if args:
        subprocess.Popen(
            [value] + args.split(),
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
    else:
        try:
            os.startfile(value)
        except Exception:
            subprocess.Popen(
                value,
                shell=True,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )


def _type_text(action: Action) -> None:
    import keyboard
    keyboard.write(action.value, delay=0.03)


def _run_command(action: Action) -> None:
    subprocess.Popen(
        action.value,
        shell=True,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )


def _media_control(action: Action) -> None:
    vk = _VK.get(action.value)
    if vk:
        _send_vk(vk)


def _send_keys(action: Action) -> None:
    import keyboard as kb
    value = action.value.strip()
    if value:
        kb.send(value)


def _toggle_topmost(hwnd: int) -> None:
    """Toggle the always-on-top flag of the given window."""
    if not hwnd:
        return
    from ctypes import wintypes
    user32 = ctypes.windll.user32

    # Explicit argtypes ensure -1/-2 are passed as full-width pointer values on 64-bit
    user32.GetWindowLongW.argtypes  = [wintypes.HWND, ctypes.c_int]
    user32.GetWindowLongW.restype   = ctypes.c_long
    user32.SetWindowPos.argtypes    = [
        wintypes.HWND, wintypes.HWND,
        ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
        ctypes.c_uint,
    ]
    user32.SetWindowPos.restype = wintypes.BOOL

    exstyle    = user32.GetWindowLongW(hwnd, _GWL_EXSTYLE)
    is_topmost = bool(exstyle & _WS_EX_TOPMOST)
    # ctypes.c_void_p(-1) = 0xFFFF…FFFF = HWND_TOPMOST
    insert_after = ctypes.c_void_p(_HWND_NOTOPMOST if is_topmost else _HWND_TOPMOST)
    user32.SetWindowPos(hwnd, insert_after, 0, 0, 0, 0, _SWP_NOMOVE | _SWP_NOSIZE)


def _replay_macro(action: Action) -> None:
    if action.value:
        from utils.macro_recorder import replay_macro
        replay_macro(action.value)


def _wait(action: Action) -> None:
    """Pause execution for the specified number of milliseconds."""
    try:
        ms = max(0, int(action.value))
    except (ValueError, TypeError):
        return
    if ms > 0:
        time.sleep(ms / 1000.0)


def _color_picker(action: Action) -> None:
    """Sample the pixel color under the cursor and copy it as #RRGGBB."""
    import ctypes.wintypes as _wt
    user32  = ctypes.windll.user32
    gdi32   = ctypes.windll.gdi32

    pt = _wt.POINT()
    user32.GetCursorPos(ctypes.byref(pt))
    hdc   = user32.GetDC(0)
    color = gdi32.GetPixel(hdc, pt.x, pt.y)
    user32.ReleaseDC(0, hdc)

    r = color & 0xFF
    g = (color >> 8)  & 0xFF
    b = (color >> 16) & 0xFF
    hex_color = f"#{r:02X}{g:02X}{b:02X}"

    _write_clipboard_text(hex_color)


def _text_transform(action: Action, trigger_hwnd: int) -> None:
    """Copy selected text, show the transform picker, then paste result."""
    import keyboard as kb
    # Bring the source window to front and copy selected text
    if trigger_hwnd:
        ctypes.windll.user32.SetForegroundWindow(trigger_hwnd)
        time.sleep(0.05)
    kb.send("ctrl+c")
    time.sleep(0.20)   # let clipboard settle
    # Schedule the picker on the main thread
    fn = _app_callbacks.get("show_transform_picker")
    if fn:
        fn(trigger_hwnd)


def _write_clipboard_text(text: str) -> None:
    """Write a string to the clipboard from any thread using Win32 API."""
    CF_UNICODETEXT = 13
    GMEM_MOVEABLE  = 0x0002
    user32   = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32
    kernel32.GlobalAlloc.restype  = ctypes.c_void_p
    kernel32.GlobalAlloc.argtypes = [ctypes.c_uint, ctypes.c_size_t]
    kernel32.GlobalLock.restype   = ctypes.c_void_p
    kernel32.GlobalLock.argtypes  = [ctypes.c_void_p]
    kernel32.GlobalUnlock.argtypes = [ctypes.c_void_p]
    kernel32.GlobalFree.argtypes   = [ctypes.c_void_p]
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


def _gemini_clipboard(action: Action) -> None:
    """Send clipboard image or text to Gemini; replace clipboard with result."""
    from core.gemini import call_gemini, clipboard_image, clipboard_text, DEFAULT_PROMPT
    key = _app_callbacks.get("get_gemini_key", lambda: "")()
    if not key:
        _write_clipboard_text(
            "[Gemini] No API key set. Add your free key in Settings → Gemini AI.")
        return
    prompt = action.value.strip() or DEFAULT_PROMPT
    try:
        img = clipboard_image()
        if img:
            result = call_gemini(key, prompt, img)
        else:
            text = clipboard_text()
            if not text.strip():
                _write_clipboard_text("[Gemini] Clipboard is empty.")
                return
            result = call_gemini(key, f"{prompt}\n\n{text}")
        _write_clipboard_text(result)
    except Exception as exc:
        _write_clipboard_text(f"[Gemini Error] {exc}")


