"""
setup.py — Run once (or from the Settings tab) to install Windows integrations:

  1. Generate a keyboard-key .ico  (assets/hotkeytool.ico)
  2. Create a Desktop shortcut     (HotkeyTool.lnk)
  3. Register the Explorer context menu entry
     "Ausgewählte Dateien in neuen Ordner bewegen"

Run:
    python setup.py              # install everything
    python setup.py --uninstall  # remove shortcut + context menu
"""

from __future__ import annotations

import os
import sys
import tempfile
import winreg
import subprocess
from pathlib import Path


# ── Paths ─────────────────────────────────────────────────────────────────────

PROJECT_DIR  = Path(__file__).parent.resolve()
ASSETS_DIR   = PROJECT_DIR / "assets"
SCRIPTS_DIR  = PROJECT_DIR / "scripts"
ICON_PATH    = ASSETS_DIR / "hotkeytool.ico"
MOVE_SCRIPT  = SCRIPTS_DIR / "move_to_folder.py"

_VERB_KEY_FILES = r"Software\Classes\*\shell\HotkeyToolMoveToFolder"
_VERB_KEY_DIRS  = r"Software\Classes\Directory\shell\HotkeyToolMoveToFolder"


# ── Helpers ───────────────────────────────────────────────────────────────────

def _pythonw() -> str:
    """Full path to pythonw.exe (windowless launcher)."""
    p = Path(sys.executable).parent / "pythonw.exe"
    return str(p) if p.exists() else sys.executable


# ── 1. Icon generation ────────────────────────────────────────────────────────

def generate_icon() -> Path:
    """Draw a 3D keyboard key with 'H' and save as multi-size .ico."""
    from PIL import Image, ImageDraw, ImageFont

    ASSETS_DIR.mkdir(exist_ok=True)

    def draw_key(size: int) -> Image.Image:
        img  = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)

        m     = max(3, size // 14)     # outer margin
        r     = max(4, size // 8)      # corner radius
        depth = max(3, size // 11)     # 3-D depth (bottom thickness)
        fi    = max(2, size // 18)     # face inset

        # Drop shadow
        so = max(1, size // 32)
        draw.rounded_rectangle(
            [m + so, m + so * 2, size - m + so, size - m + so],
            radius=r, fill=(0, 0, 0, 90),
        )

        # Key outer body (dark — the sides/bottom are visible)
        draw.rounded_rectangle(
            [m, m, size - m, size - m],
            radius=r, fill=(30, 33, 52, 255),
        )

        # Key front face (light — the "press-down" surface)
        face_t = m + fi
        face_b = size - m - fi - depth
        face_r = max(2, r - fi)
        draw.rounded_rectangle(
            [m + fi, face_t, size - m - fi, face_b],
            radius=face_r, fill=(228, 228, 245, 255),
        )

        # Highlight strip on top of face
        hl_h = max(2, size // 22)
        draw.rounded_rectangle(
            [m + fi, face_t, size - m - fi, face_t + hl_h * 2],
            radius=face_r, fill=(255, 255, 255, 150),
        )

        # "H" letter — centred on face
        cx = size / 2
        cy = (face_t + face_b) / 2 - size * 0.015

        font_size = max(8, int(size * 0.44))
        font: ImageFont.FreeTypeFont | None = None
        for fname in ("arialbd.ttf", "arial.ttf", "segoeuib.ttf", "calibrib.ttf"):
            try:
                font = ImageFont.truetype(fname, font_size)
                break
            except OSError:
                pass
        if font is None:
            font = ImageFont.load_default()

        # Subtle text shadow
        draw.text((cx + size / 70, cy + size / 70), "H",
                  fill=(0, 0, 60, 55), font=font, anchor="mm")
        # Main letter
        draw.text((cx, cy), "H",
                  fill=(25, 38, 120, 255), font=font, anchor="mm")

        return img

    sizes = [16, 24, 32, 48, 64, 128, 256]
    images = [draw_key(s) for s in sizes]

    # PIL saves ICO with multiple sizes when you pass append_images
    images[-1].save(
        str(ICON_PATH),
        format="ICO",
        append_images=images[:-1],
        sizes=[(s, s) for s in sizes],
    )
    print(f"  Icon: {ICON_PATH}")
    return ICON_PATH


# ── 2. Desktop shortcut ───────────────────────────────────────────────────────

def create_desktop_shortcut() -> None:
    """Create HotkeyTool.lnk on the user's Desktop via a temp PowerShell script."""
    desktop       = Path(os.environ.get("USERPROFILE", Path.home())) / "Desktop"
    shortcut_path = desktop / "HotkeyTool.lnk"
    pythonw       = _pythonw()
    main_script   = str(PROJECT_DIR / "main.py")
    icon_str      = f"{ICON_PATH},0"

    # Use single-quoted PS strings → backslashes and spaces are safe
    ps = f"""
$sh = New-Object -ComObject WScript.Shell
$lnk = $sh.CreateShortcut('{shortcut_path}')
$lnk.TargetPath      = '{pythonw}'
$lnk.Arguments       = '"{main_script}"'
$lnk.WorkingDirectory = '{PROJECT_DIR}'
$lnk.IconLocation    = '{icon_str}'
$lnk.Description     = 'HotkeyTool - Global hotkey manager'
$lnk.Save()
""".strip()

    # Write to a temp .ps1 to avoid shell-escaping nightmares
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".ps1", delete=False, encoding="utf-8"
    ) as tf:
        tf.write(ps)
        tf_path = tf.name

    try:
        subprocess.run(
            [
                "powershell",
                "-NoProfile", "-NonInteractive",
                "-ExecutionPolicy", "Bypass",
                "-File", tf_path,
            ],
            check=True,
            capture_output=True,
        )
    finally:
        os.unlink(tf_path)

    print(f"  Shortcut: {shortcut_path}")


def remove_desktop_shortcut() -> None:
    desktop       = Path(os.environ.get("USERPROFILE", Path.home())) / "Desktop"
    shortcut_path = desktop / "HotkeyTool.lnk"
    if shortcut_path.exists():
        shortcut_path.unlink()
        print(f"  Removed shortcut: {shortcut_path}")
    else:
        print("  No shortcut found.")


# ── 3. Context menu ───────────────────────────────────────────────────────────

def register_context_menu() -> None:
    """
    Register the Explorer right-click verb for files AND folders under HKCU
    (no admin required).
    """
    pythonw = _pythonw()
    script  = str(MOVE_SCRIPT)
    command = f'"{pythonw}" "{script}" "%1"'
    label   = "Ausgew\u00e4hlte Dateien in neuen Ordner bewegen"
    icon    = f"{ICON_PATH},0"

    for verb_key in (_VERB_KEY_FILES, _VERB_KEY_DIRS):
        cmd_key = verb_key + r"\command"
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, verb_key) as k:
            winreg.SetValueEx(k, "",                 0, winreg.REG_SZ, label)
            winreg.SetValueEx(k, "MultiSelectModel", 0, winreg.REG_SZ, "Player")
            winreg.SetValueEx(k, "Icon",             0, winreg.REG_SZ, icon)
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, cmd_key) as k:
            winreg.SetValueEx(k, "", 0, winreg.REG_SZ, command)
        print(f"  Context menu registered: {verb_key}")


def unregister_context_menu() -> None:
    for verb_key in (_VERB_KEY_FILES, _VERB_KEY_DIRS):
        try:
            winreg.DeleteKey(
                winreg.HKEY_CURRENT_USER, verb_key + r"\command"
            )
        except OSError:
            pass
        try:
            winreg.DeleteKey(winreg.HKEY_CURRENT_USER, verb_key)
        except OSError:
            pass
    print("  Context menu entries removed.")


# ── 4. Windows 11 classic context menu ───────────────────────────────────────
#
# Windows 11 22H2+ uses a new simplified context menu by default.
# Custom shell verbs registered via HKCU\...\shell\ only appear there when the
# user clicks "Show more options".  There is no supported way to add arbitrary
# script commands to the new menu without a COM DLL or MSIX package.
#
# The standard solution (used by many third-party apps) is to restore the
# classic Windows 10 context menu via a single HKCU registry key.
# No admin rights required; Explorer must be restarted for it to take effect.

_WIN11_CLASSIC_KEY = (
    r"Software\Classes\CLSID"
    r"\{86ca1aa0-34aa-4e8b-a509-50c905bae2a2}"
    r"\InprocServer32"
)
_WIN11_CLASSIC_PARENT = (
    r"Software\Classes\CLSID"
    r"\{86ca1aa0-34aa-4e8b-a509-50c905bae2a2}"
)


def enable_classic_context_menu() -> None:
    """Restore Windows 10-style context menu on Windows 11."""
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, _WIN11_CLASSIC_KEY) as k:
        winreg.SetValueEx(k, "", 0, winreg.REG_SZ, "")
    print("  Classic context menu enabled (Explorer restart required).")


def disable_classic_context_menu() -> None:
    """Revert to the Windows 11 simplified context menu."""
    try:
        winreg.DeleteKey(winreg.HKEY_CURRENT_USER, _WIN11_CLASSIC_KEY)
    except OSError:
        pass
    try:
        winreg.DeleteKey(winreg.HKEY_CURRENT_USER, _WIN11_CLASSIC_PARENT)
    except OSError:
        pass
    print("  Windows 11 context menu restored (Explorer restart required).")


def classic_context_menu_enabled() -> bool:
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _WIN11_CLASSIC_KEY):
            return True
    except OSError:
        return False


def restart_explorer() -> None:
    """Kill and restart explorer.exe so context menu changes take effect immediately."""
    subprocess.Popen(
        "taskkill /F /IM explorer.exe && start explorer.exe",
        shell=True,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )


# ── Status checks ─────────────────────────────────────────────────────────────

def shortcut_exists() -> bool:
    desktop = Path(os.environ.get("USERPROFILE", Path.home())) / "Desktop"
    return (desktop / "HotkeyTool.lnk").exists()


def context_menu_registered() -> bool:
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _VERB_KEY_FILES):
            return True
    except OSError:
        return False


# ── CLI entry-point ───────────────────────────────────────────────────────────

def install() -> None:
    print("HotkeyTool Setup — Installing Windows integrations")
    print("=" * 52)
    generate_icon()
    create_desktop_shortcut()
    register_context_menu()
    print("=" * 52)
    print("Done.")
    print("  • Launch HotkeyTool from your Desktop")
    print("  • Right-click selected files/folders in Explorer")
    print("    -> Ausgewählte Dateien in neuen Ordner bewegen")


def uninstall() -> None:
    print("HotkeyTool Setup — Removing Windows integrations")
    print("=" * 52)
    remove_desktop_shortcut()
    unregister_context_menu()
    print("=" * 52)
    print("Done.")


if __name__ == "__main__":
    if "--uninstall" in sys.argv:
        uninstall()
    else:
        install()
