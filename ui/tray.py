from __future__ import annotations

import threading
from pathlib import Path
from typing import TYPE_CHECKING

import pystray
from PIL import Image

from ui.icons import brand_logo

if TYPE_CHECKING:
    from app import App


# Get the path relative to this script
ASSETS_PATH = Path(__file__).parent.parent / "assets" / "hotkeytool.ico"

class TrayIcon:
    def __init__(self, app: "App") -> None:
        self.app = app
        self._icon: pystray.Icon | None = None
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        img = Image.open(ASSETS_PATH)
        self._icon = pystray.Icon(
            "HotkeyTool",
            img,
            "HotkeyTool",
            menu=self._build_menu(),
        )
        self._thread = threading.Thread(target=self._icon.run, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        if self._icon:
            try:
                self._icon.stop()
            except Exception:
                pass

    def update_menu(self) -> None:
        if self._icon:
            try:
                self._icon.menu = self._build_menu()
                self._icon.update_menu()
            except Exception:
                pass

    # ── menu ─────────────────────────────────────────────────────────────────

    def _build_menu(self) -> pystray.Menu:
        running = self.app.listener.is_running()
        listen_label = "Listening: ON  \u2713" if running else "Listening: OFF"

        return pystray.Menu(
            pystray.MenuItem("Show Window", self._on_show, default=True),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(listen_label, self._on_toggle_listening),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Quick Notes", self._on_show_notes),
            pystray.MenuItem("System Stats", self._on_toggle_stats),
            pystray.MenuItem("Clipboard History", self._on_show_clipboard),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Quit", self._on_quit),
        )

    # ── callbacks (tray thread) ───────────────────────────────────────────────

    def _on_show(self, icon: pystray.Icon, item: pystray.MenuItem) -> None:
        self.app.show_window()

    def _on_toggle_listening(self, icon: pystray.Icon, item: pystray.MenuItem) -> None:
        root = self.app.window
        if root:
            root.after(0, self.app.toggle_listening)

    def _on_show_notes(self, icon, item) -> None:
        self.app.toggle_notes_window()

    def _on_toggle_stats(self, icon, item) -> None:
        self.app.toggle_stats_widget()

    def _on_show_clipboard(self, icon, item) -> None:
        root = self.app.window
        if root:
            root.after(0, self._do_show_clipboard)

    def _do_show_clipboard(self) -> None:
        self.app.show_window()
        if self.app.window:
            try:
                self.app.window._tabs.set("Clipboard")
            except Exception:
                pass

    def _on_quit(self, icon: pystray.Icon, item: pystray.MenuItem) -> None:
        root = self.app.window
        if root:
            root.after(0, self.app.quit)
