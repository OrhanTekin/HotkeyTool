"""
Window layout manager: captures and restores the positions/sizes of all
visible top-level windows using ctypes + Win32 APIs.
No admin rights required for windows owned by the current user.
"""
from __future__ import annotations

import ctypes
import ctypes.wintypes as wt
import os
from typing import List, Optional

from core.models import WindowLayout, WindowState

_user32   = ctypes.windll.user32
_kernel32 = ctypes.windll.kernel32
_psapi    = ctypes.windll.psapi

# Window styles
_WS_VISIBLE    = 0x10000000
_GWL_STYLE     = -16
_WS_MINIMIZE   = 0x20000000

# ShowWindow commands
_SW_RESTORE    = 9
_SW_MAXIMIZE   = 3

# ── helpers ──────────────────────────────────────────────────────────────────

def _get_exe(hwnd: int) -> str:
    pid = wt.DWORD()
    _user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    h = _kernel32.OpenProcess(0x0410, False, pid.value)  # PROCESS_QUERY_INFO|VM_READ
    if not h:
        return ""
    buf = ctypes.create_unicode_buffer(260)
    try:
        _psapi.GetModuleFileNameExW(h, None, buf, 260)
        return os.path.basename(buf.value)
    except Exception:
        return ""
    finally:
        _kernel32.CloseHandle(h)


def _is_capturable(hwnd: int) -> bool:
    if not _user32.IsWindowVisible(hwnd):
        return False
    # Skip windows with no title
    length = _user32.GetWindowTextLengthW(hwnd)
    if length == 0:
        return False
    # Skip minimized
    style = _user32.GetWindowLongW(hwnd, _GWL_STYLE)
    if style & _WS_MINIMIZE:
        return False
    # Skip the taskbar, desktop, etc.
    buf = ctypes.create_unicode_buffer(256)
    _user32.GetClassNameW(hwnd, buf, 256)
    skip_classes = {"Shell_TrayWnd", "Progman", "WorkerW", "DV2ControlHost"}
    return buf.value not in skip_classes


# ── public API ────────────────────────────────────────────────────────────────

def capture_layout(name: str) -> WindowLayout:
    """Snapshot all visible capturable windows and return a WindowLayout."""
    layout = WindowLayout.new(name)
    windows: List[WindowState] = []

    EnumWindowsProc = ctypes.WINFUNCTYPE(ctypes.c_bool, wt.HWND, wt.LPARAM)

    def _callback(hwnd, _):
        if not _is_capturable(hwnd):
            return True
        rect = wt.RECT()
        _user32.GetWindowRect(hwnd, ctypes.byref(rect))
        title_buf = ctypes.create_unicode_buffer(256)
        _user32.GetWindowTextW(hwnd, title_buf, 256)
        exe = _get_exe(hwnd)
        style = _user32.GetWindowLongW(hwnd, _GWL_STYLE)
        maximized = bool(style & 0x01000000)  # WS_MAXIMIZE
        windows.append(WindowState(
            title     = title_buf.value,
            exe       = exe,
            x         = rect.left,
            y         = rect.top,
            width     = rect.right  - rect.left,
            height    = rect.bottom - rect.top,
            maximized = maximized,
        ))
        return True

    _user32.EnumWindows(EnumWindowsProc(_callback), 0)
    layout.windows = windows
    return layout


def restore_layout(layout: WindowLayout) -> tuple[int, int]:
    """
    Restore window positions. Matches by exe name + partial title.
    Returns (matched, total) counts.
    """
    matched = 0
    total   = len(layout.windows)

    EnumWindowsProc = ctypes.WINFUNCTYPE(ctypes.c_bool, wt.HWND, wt.LPARAM)
    live_windows: list[tuple[int, str, str]] = []  # (hwnd, title, exe)

    def _enum(hwnd, _):
        if _user32.IsWindowVisible(hwnd):
            title_buf = ctypes.create_unicode_buffer(256)
            _user32.GetWindowTextW(hwnd, title_buf, 256)
            live_windows.append((hwnd, title_buf.value, _get_exe(hwnd)))
        return True

    _user32.EnumWindows(EnumWindowsProc(_enum), 0)

    for ws in layout.windows:
        hwnd = _find_window(live_windows, ws)
        if not hwnd:
            continue
        try:
            if ws.maximized:
                _user32.ShowWindow(hwnd, _SW_MAXIMIZE)
            else:
                _user32.ShowWindow(hwnd, _SW_RESTORE)
                _user32.MoveWindow(hwnd, ws.x, ws.y, ws.width, ws.height, True)
            matched += 1
        except Exception:
            pass

    return matched, total


def _find_window(live: list, ws: WindowState) -> Optional[int]:
    """Find the best matching live window for a saved WindowState."""
    # Exact exe + title match
    for hwnd, title, exe in live:
        if exe == ws.exe and title == ws.title:
            return hwnd
    # Exe match + title starts-with
    for hwnd, title, exe in live:
        if exe == ws.exe and ws.title and title.startswith(ws.title[:20]):
            return hwnd
    # Exe match only
    for hwnd, title, exe in live:
        if exe == ws.exe:
            return hwnd
    return None
