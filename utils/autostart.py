import os
import sys
import winreg

_RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
_APP_NAME = "HotkeyTool"


def _launch_command() -> str:
    if getattr(sys, "frozen", False):
        return f'"{sys.executable}" --tray'
    # pythonw.exe suppresses the console window on Windows
    exe = sys.executable
    pythonw = os.path.join(os.path.dirname(exe),
                           "pythonw.exe" if os.name == "nt" else os.path.basename(exe))
    if not os.path.isfile(pythonw):
        pythonw = exe
    script = os.path.abspath(sys.argv[0])
    return f'"{pythonw}" "{script}" --tray'


def is_autostart_enabled() -> bool:
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY, 0, winreg.KEY_READ) as key:
            winreg.QueryValueEx(key, _APP_NAME)
            return True
    except OSError:
        return False


def enable_autostart() -> None:
    cmd = _launch_command()
    with winreg.OpenKey(
        winreg.HKEY_CURRENT_USER, _RUN_KEY, 0, winreg.KEY_SET_VALUE
    ) as key:
        winreg.SetValueEx(key, _APP_NAME, 0, winreg.REG_SZ, cmd)


def disable_autostart() -> None:
    try:
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, _RUN_KEY, 0, winreg.KEY_SET_VALUE
        ) as key:
            winreg.DeleteValue(key, _APP_NAME)
    except OSError:
        pass
