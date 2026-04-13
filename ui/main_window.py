from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

import customtkinter as ctk

if TYPE_CHECKING:
    from app import App


class MainWindow(ctk.CTk):
    def __init__(self, app: "App") -> None:
        super().__init__()
        self.app = app

        self.title("HotkeyTool")
        self.geometry("1060x620")
        self.minsize(860, 520)

        # Window icon
        try:
            from PIL import Image, ImageTk
            from ui.tray import _make_icon_image
            pil_img = _make_icon_image().resize((32, 32))
            self._icon_photo = ImageTk.PhotoImage(pil_img)
            self.iconphoto(True, self._icon_photo)
        except Exception:
            pass

        self._build()
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    # ── layout ────────────────────────────────────────────────────────────────

    def _build(self) -> None:
        from ui.bindings_tab  import BindingsTab
        from ui.settings_tab  import SettingsTab
        from ui.schedules_tab import SchedulesTab
        from ui.clipboard_tab import ClipboardTab
        from ui.snippets_tab  import SnippetsTab
        from ui.timer_tab     import TimerTab

        # ── Header bar ──
        header = ctk.CTkFrame(self, height=56, corner_radius=0,
                               fg_color=("#0d0d1e", "#0d0d1e"))
        header.pack(fill="x", side="top")
        header.pack_propagate(False)

        ctk.CTkLabel(
            header, text="\u2328  HotkeyTool",
            font=ctk.CTkFont(size=20, weight="bold"),
            text_color=("#5b9bd5", "#5b9bd5"),
        ).pack(side="left", padx=18, pady=12)

        ctk.CTkLabel(
            header, text="Global hotkey manager & productivity suite",
            font=ctk.CTkFont(size=11),
            text_color=("#444466", "#444466"),
        ).pack(side="left", padx=4)

        # Quick-access buttons in header
        ctk.CTkButton(
            header, text="Notes", width=72, height=30,
            font=ctk.CTkFont(size=11),
            fg_color=("#1e2a3a", "#1e2a3a"), hover_color=("#2a3a4a", "#2a3a4a"),
            command=self.app.show_notes_window,
        ).pack(side="right", padx=(4, 16))

        ctk.CTkButton(
            header, text="Stats", width=60, height=30,
            font=ctk.CTkFont(size=11),
            fg_color=("#1e2a3a", "#1e2a3a"), hover_color=("#2a3a4a", "#2a3a4a"),
            command=self.app.toggle_stats_widget,
        ).pack(side="right", padx=2)

        # ── Tab view ──
        self._tabs = ctk.CTkTabview(self, corner_radius=8)
        self._tabs.pack(fill="both", expand=True, padx=12, pady=(8, 0))

        for tab_name in ("Bindings", "Schedules", "Clipboard", "Snippets", "Timer", "Settings"):
            self._tabs.add(tab_name)

        self._bindings_tab  = BindingsTab (self._tabs.tab("Bindings"),  self.app)
        self._bindings_tab.pack(fill="both", expand=True)

        self._schedules_tab = SchedulesTab(self._tabs.tab("Schedules"), self.app)
        self._schedules_tab.pack(fill="both", expand=True)

        self._clipboard_tab = ClipboardTab(self._tabs.tab("Clipboard"), self.app)
        self._clipboard_tab.pack(fill="both", expand=True)

        self._snippets_tab  = SnippetsTab (self._tabs.tab("Snippets"),  self.app)
        self._snippets_tab.pack(fill="both", expand=True)

        self._timer_tab     = TimerTab    (self._tabs.tab("Timer"),     self.app)
        self._timer_tab.pack(fill="both", expand=True)

        self._settings_tab  = SettingsTab (self._tabs.tab("Settings"),  self.app)
        self._settings_tab.pack(fill="both", expand=True)

        # ── Status bar ──
        sb = ctk.CTkFrame(self, height=26, corner_radius=0,
                          fg_color=("#0a0a18", "#0a0a18"))
        sb.pack(fill="x", side="bottom")
        sb.pack_propagate(False)

        self._status = ctk.CTkLabel(
            sb, text="Ready",
            font=ctk.CTkFont(size=11),
            text_color=("#555577", "#555577"),
            anchor="w",
        )
        self._status.pack(side="left", padx=14, pady=4)

    # ── public API ────────────────────────────────────────────────────────────

    def update_status(self, text: str) -> None:
        ts = datetime.now().strftime("%H:%M:%S")
        self._status.configure(text=f"{text}   ({ts})")

    def refresh_bindings(self) -> None:
        self._bindings_tab.refresh()

    def refresh_schedules(self) -> None:
        self._schedules_tab.refresh()

    def update_listening_state(self) -> None:
        self._bindings_tab.update_listening_button()

    # ── close protocol ────────────────────────────────────────────────────────

    def _on_close(self) -> None:
        if self.app.config.settings.minimize_to_tray_on_close:
            self.withdraw()
        else:
            self.app.quit()
