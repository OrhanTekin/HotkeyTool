"""
Entry point for HotkeyTool.

Enforces single-instance via a named Windows mutex so that
opening the app twice just brings the existing window to focus.
"""
import ctypes
import sys


def _enable_dpi_awareness() -> None:
    """Tell Windows we'll handle DPI ourselves, so the window isn't bitmap-
    scaled to a blurry mess on HiDPI displays. Must run before any Tk window
    is created. Tries Per-Monitor-V2 → Per-Monitor → System in that order.
    """
    if sys.platform != "win32":
        return
    try:
        # Win 10 1703+. -4 = DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2
        if ctypes.windll.user32.SetProcessDpiAwarenessContext(-4):
            return
    except Exception:
        pass
    try:
        # Win 8.1+. 2 = PROCESS_PER_MONITOR_DPI_AWARE
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
        return
    except Exception:
        pass
    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass


def _single_instance_check() -> None:
    ERROR_ALREADY_EXISTS = 183
    mutex = ctypes.windll.kernel32.CreateMutexW(None, False, "HotkeyToolSingleInstanceMutex")
    if ctypes.windll.kernel32.GetLastError() == ERROR_ALREADY_EXISTS:
        ctypes.windll.user32.MessageBoxW(
            0,
            "HotkeyTool is already running.\nCheck the system tray.",
            "HotkeyTool",
            0x40,  # MB_ICONINFORMATION
        )
        sys.exit(0)
    # Keep mutex alive for the lifetime of the process
    return mutex  # noqa: F821  (intentional leak — keeps the handle open)


def main() -> None:
    _enable_dpi_awareness()
    _mutex = _single_instance_check()  # noqa: F841

    try:
        import keyboard  # noqa: F401  — early import to surface install issues
    except ImportError:
        ctypes.windll.user32.MessageBoxW(
            0,
            "Required package 'keyboard' is not installed.\n\n"
            "Run:  pip install -r requirements.txt",
            "HotkeyTool — Missing dependency",
            0x10,  # MB_ICONERROR
        )
        sys.exit(1)

    from app import App
    tray_only = "--tray" in sys.argv
    App(tray_only=tray_only).run()


if __name__ == "__main__":
    main()
