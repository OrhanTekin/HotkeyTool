"""
move_to_folder.py
─────────────────
Called by the Windows Explorer context menu entry
"Ausgewählte Dateien in neuen Ordner bewegen".

Windows invokes this script ONCE PER selected file (MultiSelectModel = Player).
All invocations are nearly simultaneous.  We use a one-file-per-worker queue
(no write contention) plus an atomic master-lock to batch all files together,
create a new folder, move everything in, then put the folder in rename mode.

Usage:
    pythonw move_to_folder.py <file_path>
"""

import ctypes
import glob
import os
import shutil
import subprocess
import sys
import time
import uuid

# ── temp-dir paths ────────────────────────────────────────────────────────────
_TEMP = os.environ.get("TEMP", os.path.expanduser("~"))
_WORKER_PREFIX  = "hotkeytool_mv_item_"
_MASTER_LOCK    = os.path.join(_TEMP, "hotkeytool_mv_master.lock")
_COLLECT_DELAY  = 0.45   # seconds to wait for all worker processes to write their files
_STALE_TIMEOUT  = 8.0    # seconds after which the master lock is considered stale/orphaned


def _msgbox(text: str, title: str = "HotkeyTool", icon: int = 0x30) -> None:
    ctypes.windll.user32.MessageBoxW(0, text, title, icon)


def _write_worker_file(path: str) -> str:
    """Write this file's path to a unique temp file.  Returns the temp file path."""
    worker_file = os.path.join(_TEMP, f"{_WORKER_PREFIX}{uuid.uuid4().hex}.txt")
    with open(worker_file, "w", encoding="utf-8") as f:
        f.write(path)
    return worker_file


def _try_become_master() -> bool:
    """
    Attempt to atomically create the master lock file.
    Returns True if this process is now the master.
    Also clears stale locks from crashed previous runs.
    """
    # Clear stale lock first
    try:
        if os.path.exists(_MASTER_LOCK):
            age = time.time() - os.path.getmtime(_MASTER_LOCK)
            if age > _STALE_TIMEOUT:
                os.remove(_MASTER_LOCK)
    except OSError:
        pass

    try:
        fd = os.open(_MASTER_LOCK, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        os.close(fd)
        return True
    except FileExistsError:
        return False


def _collect_files() -> list[str]:
    """Read all worker files, delete them, return unique existing paths."""
    pattern = os.path.join(_TEMP, f"{_WORKER_PREFIX}*.txt")
    files: list[str] = []
    for wf in glob.glob(pattern):
        try:
            with open(wf, "r", encoding="utf-8") as f:
                p = f.read().strip()
            os.remove(wf)
            if p and os.path.exists(p):
                files.append(p)
        except OSError:
            pass
    # Deduplicate while preserving order
    seen: set[str] = set()
    result: list[str] = []
    for p in files:
        norm = os.path.normpath(p)
        if norm not in seen:
            seen.add(norm)
            result.append(norm)
    return result


def _unique_folder(parent: str, base_name: str) -> str:
    """Return a path for a new folder that does not yet exist."""
    path = os.path.join(parent, base_name)
    counter = 2
    while os.path.exists(path):
        path = os.path.join(parent, f"{base_name} ({counter})")
        counter += 1
    return path


def _open_and_rename(folder_path: str) -> None:
    """
    1. Use SHOpenFolderAndSelectItems to open the parent folder and select
       the new folder — works correctly with any path (spaces, special chars).
    2. Find the Explorer window HWND, bring it to foreground.
    3. Send F2 to enter rename mode.
    """
    import ctypes
    from ctypes import wintypes

    shell32 = ctypes.windll.shell32
    user32  = ctypes.windll.user32

    # ── Select the folder in Explorer ─────────────────────────────────────
    ILCreateFromPathW          = shell32.ILCreateFromPathW
    ILCreateFromPathW.restype  = ctypes.c_void_p
    ILCreateFromPathW.argtypes = [wintypes.LPCWSTR]

    ILFree          = shell32.ILFree
    ILFree.restype  = None
    ILFree.argtypes = [ctypes.c_void_p]

    pidl = ILCreateFromPathW(folder_path)
    if pidl:
        # cidl=0 → Windows opens the PARENT of pidl and selects pidl itself
        shell32.SHOpenFolderAndSelectItems(ctypes.c_void_p(pidl), 0, None, 0)
        ILFree(ctypes.c_void_p(pidl))
    else:
        # Fallback (should never be needed for a valid path)
        subprocess.Popen(f'explorer.exe /select,"{folder_path}"', shell=True)

    # ── Wait for Explorer to render ────────────────────────────────────────
    time.sleep(1.0)

    # ── Find the Explorer window and bring it to foreground ───────────────
    _EXPLORER_CLASS = "CabinetWClass"
    hwnd_found = [0]

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def _enum_cb(hwnd: int, _: int) -> bool:
        buf = ctypes.create_unicode_buffer(256)
        user32.GetClassNameW(hwnd, buf, 256)
        if buf.value == _EXPLORER_CLASS:
            hwnd_found[0] = hwnd   # keep last (most-recently-opened)
        return True

    user32.EnumWindows(_enum_cb, 0)

    if hwnd_found[0]:
        user32.SetForegroundWindow(hwnd_found[0])
        time.sleep(0.3)

    # ── Trigger rename mode ────────────────────────────────────────────────
    try:
        import keyboard
        keyboard.send("f2")
    except Exception:
        pass


def main() -> None:
    if len(sys.argv) < 2:
        sys.exit(0)

    file_path = os.path.normpath(sys.argv[1])
    if not os.path.exists(file_path):
        sys.exit(0)

    # ── Step 1: each worker deposits its file path ──
    _write_worker_file(file_path)

    # ── Step 2: elect a single master process ──
    if not _try_become_master():
        # Another process is handling it — we're done
        sys.exit(0)

    # ── Step 3 (master only): wait for all workers to finish writing ──
    time.sleep(_COLLECT_DELAY)

    # ── Step 4: collect all queued files ──
    files = _collect_files()

    # Release the master lock
    try:
        os.remove(_MASTER_LOCK)
    except OSError:
        pass

    if not files:
        sys.exit(0)

    parent_dir = os.path.dirname(files[0])

    # ── Step 5: create the new folder ──
    new_folder = _unique_folder(parent_dir, "Neuer Ordner")
    try:
        os.makedirs(new_folder)
    except OSError as exc:
        _msgbox(f"Ordner konnte nicht erstellt werden:\n{exc}", icon=0x10)
        sys.exit(1)

    # ── Step 6: move all files into it ──
    errors: list[str] = []
    for f in files:
        try:
            shutil.move(f, new_folder)
        except Exception as exc:
            errors.append(f"{os.path.basename(f)}: {exc}")

    if errors:
        _msgbox(
            "Einige Elemente konnten nicht verschoben werden:\n\n" + "\n".join(errors),
            title="HotkeyTool",
            icon=0x30,
        )

    # ── Step 7: open Explorer, select folder, trigger rename ──
    _open_and_rename(new_folder)


if __name__ == "__main__":
    main()
