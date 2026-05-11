import sys
from pathlib import Path


def resource_path(relative: str) -> Path:
    """Resolve path to a bundled asset. Works for dev and PyInstaller frozen."""
    base = getattr(sys, "_MEIPASS", None)
    if base:
        return Path(base) / relative
    return Path(__file__).parent.parent / relative


def apply_window_icon(window) -> None:
    """Apply HotkeyTool's .ico to a Tk Toplevel/CTk window's title bar.

    Safe to call on any window; silently does nothing if the icon file is
    missing.  Call via `self.after(200, lambda: apply_window_icon(self))`
    on Toplevel windows — on Windows, iconbitmap can fail if invoked before
    the native window handle is fully created.
    """
    try:
        ico_path = resource_path("assets/hotkeytool.ico")
        if ico_path.exists():
            window.iconbitmap(str(ico_path))
    except Exception:
        pass
