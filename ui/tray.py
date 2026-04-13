from __future__ import annotations

import threading
from typing import TYPE_CHECKING

import pystray
from PIL import Image, ImageDraw, ImageFilter

if TYPE_CHECKING:
    from app import App


def _make_icon_image(size: int = 64) -> Image.Image:
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    pad = max(2, size // 32)
    r = max(8, size // 8)

    # Dark background
    draw.rounded_rectangle([pad, pad, size - pad, size - pad], radius=r, fill=(13, 15, 35, 255))

    # Lightning bolt points (normalised 0..1 → pixels)
    bolt_norm = [
        (0.58, 0.08),
        (0.32, 0.50),
        (0.52, 0.50),
        (0.38, 0.92),
        (0.66, 0.48),
        (0.47, 0.48),
        (0.72, 0.08),
    ]
    m = size * 0.12
    w = size - 2 * m
    bolt_px = [(m + x * w, m + y * w) for x, y in bolt_norm]

    # Glow layer
    glow = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    ImageDraw.Draw(glow).polygon(bolt_px, fill=(80, 180, 255, 160))
    glow = glow.filter(ImageFilter.GaussianBlur(radius=max(2, size // 20)))
    img = Image.alpha_composite(img, glow)

    # Main bolt
    draw2 = ImageDraw.Draw(img)
    draw2.polygon(bolt_px, fill=(100, 200, 255, 255))

    # Bright inner highlight
    cx = sum(p[0] for p in bolt_px) / len(bolt_px)
    cy = sum(p[1] for p in bolt_px) / len(bolt_px)
    inner = [(cx + (x - cx) * 0.85, cy + (y - cy) * 0.85) for x, y in bolt_px]
    draw2.polygon(inner, fill=(200, 235, 255, 220))

    return img


class TrayIcon:
    def __init__(self, app: "App") -> None:
        self.app = app
        self._icon: pystray.Icon | None = None
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        img = _make_icon_image()
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
        self.app.show_notes_window()

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
