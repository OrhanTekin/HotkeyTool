"""
App — central controller.

Owns the config, listener, window, tray, scheduler, clipboard manager,
snippet expander, notes window, stats widget, and stats monitor.
All cross-thread calls that need to reach the UI go through window.after(0, callable).
"""
from __future__ import annotations

import time
import threading
from typing import Optional

import customtkinter as ctk

from core.action_runner import run_actions, register_app_callback
from core.clipboard_manager import ClipboardManager
from core.config import load_config, save_config
from core.hotkey_listener import HotkeyListener
from core.models import AppConfig
from core.scheduler import SchedulerService
from core.snippet_expander import SnippetExpander
from core.stats_monitor import StatsMonitor


class App:
    def __init__(self, tray_only: bool = False) -> None:
        self.config: AppConfig = load_config()
        self._tray_only = tray_only

        self.listener = HotkeyListener(
            get_bindings=lambda: self.config.bindings,
            on_triggered=self._on_hotkey_triggered,
        )
        self.scheduler = SchedulerService(
            get_config=lambda: self.config,
            run_binding=lambda b: run_actions(list(b.actions)),
        )
        self.clipboard = ClipboardManager()
        self.clipboard._history = list(self.config.clipboard_history[:10])
        self.snippets  = SnippetExpander(
            get_snippets=lambda: self.config.snippets,
        )
        self.stats_monitor: StatsMonitor | None = None

        self.window: Optional[ctk.CTk]    = None
        self.notes_win                    = None   # NotesWindow (lazy-created)
        self.stats_widget                 = None   # StatsWidget (lazy-created)
        self._tray                        = None

        # Register callbacks so action_runner can reach UI-level services
        register_app_callback("toggle_stats_widget",  self._cb_toggle_stats)
        register_app_callback("show_notes_window",    self._cb_show_notes)
        register_app_callback("show_transform_picker", self._cb_show_transform_picker)

    # ── lifecycle ─────────────────────────────────────────────────────────────

    def run(self) -> None:
        from ui.main_window import MainWindow
        from ui.tray import TrayIcon

        ctk.set_appearance_mode(self.config.settings.theme)
        ctk.set_default_color_theme("blue")

        self.window = MainWindow(self)
        if self._tray_only:
            self.window.withdraw()

        # Lazy-create floating windows (they need a root window to exist first)
        from ui.stats_widget import StatsWidget
        from ui.notes_window import NotesWindow
        self.stats_widget = StatsWidget(self)
        self.notes_win    = NotesWindow(self)

        self._tray = TrayIcon(self)
        self._tray.start()

        if self.config.listening:
            self.listener.start()
            self.window.update_listening_state()

        self.scheduler.start()
        self.clipboard.start()
        self.snippets.start()

        # Stats monitor
        self.stats_monitor = StatsMonitor(self._on_stats_update)
        self.stats_monitor.start()
        self._start_sleep_detector()
        if self.config.settings.stats_widget_on_startup:
            self.stats_widget.show()

        self.window.mainloop()

        # ── cleanup ──
        self.listener.stop()
        self.scheduler.stop()
        self.clipboard.stop()
        self.snippets.stop()
        if self.stats_monitor:
            self.stats_monitor.stop()
        try:
            if self._tray:
                self._tray.stop()
        except Exception:
            pass

    # ── window visibility ─────────────────────────────────────────────────────

    def show_window(self) -> None:
        if self.window:
            self.window.after(0, self._do_show)

    def _do_show(self) -> None:
        if self.window:
            self.window.deiconify()
            self.window.lift()
            self.window.focus_force()

    def hide_window(self) -> None:
        if self.window:
            self.window.withdraw()

    # ── listening toggle ──────────────────────────────────────────────────────

    def toggle_listening(self) -> None:
        if self.listener.is_running():
            self.listener.stop()
            self.config.listening = False
        else:
            self.listener.start()
            self.config.listening = True
        save_config(self.config)
        if self.window:
            self.window.update_listening_state()
        if self._tray:
            self._tray.update_menu()

    # ── save helpers ──────────────────────────────────────────────────────────

    def save_and_reload(self) -> None:
        """Save config + reload hotkey listener + refresh bindings tab."""
        save_config(self.config)
        self.listener.reload()
        if self.window:
            self.window.refresh_bindings()

    def save_and_reload_schedules(self) -> None:
        save_config(self.config)
        if self.window:
            self.window.refresh_schedules()

    def save_config_only(self) -> None:
        """Save without reloading the listener (for non-binding changes)."""
        save_config(self.config)

    # ── quit ──────────────────────────────────────────────────────────────────

    def quit(self) -> None:
        # Persist clipboard history before destroying the window
        self.config.clipboard_history = self.clipboard.history[:10]
        save_config(self.config)
        if self.window:
            self.window.destroy()

    # ── notes ─────────────────────────────────────────────────────────────────

    def show_notes_window(self) -> None:
        if self.notes_win and self.window:
            self.window.after(0, self.notes_win.show)

    def toggle_notes_window(self) -> None:
        if self.notes_win and self.window:
            self.window.after(0, self.notes_win.toggle)

    def _cb_show_notes(self) -> None:
        self.toggle_notes_window()

    # ── transform picker ──────────────────────────────────────────────────────

    def _cb_show_transform_picker(self, trigger_hwnd: int) -> None:
        """Called from action_runner daemon thread; schedules picker on main thread."""
        if self.window:
            self.window.after(0, lambda: self._open_transform_picker(trigger_hwnd))

    def _open_transform_picker(self, trigger_hwnd: int) -> None:
        from ui.transform_picker import TransformPicker
        TransformPicker(self, trigger_hwnd)

    # ── stats widget ──────────────────────────────────────────────────────────

    def toggle_stats_widget(self) -> None:
        if self.stats_widget and self.window:
            self.window.after(0, self.stats_widget.toggle)

    def _cb_toggle_stats(self) -> None:
        self.toggle_stats_widget()

    def _on_stats_update(self, stats) -> None:
        if self.stats_widget and self.window:
            self.window.after(0, lambda: self.stats_widget.update_stats(stats))

    # ── sleep / wake recovery ─────────────────────────────────────────────────

    def on_system_resume(self) -> None:
        """Called when the PC wakes from sleep.

        Windows drops all WH_KEYBOARD_LL hooks while suspended.
        keyboard.remove_all_hotkeys() only clears Python callbacks — the
        library's listener thread stays alive with a dead hook, so the next
        add_hotkey() call never reinstalls it.  keyboard.unhook_all() fully
        tears down the internals so the next add_hotkey() starts fresh.
        """
        # Cooldown: WNDPROC and the time-jump detector can both fire; ignore
        # any duplicate call within 10 seconds of the first one.
        now = time.monotonic()
        if now - getattr(self, "_last_resume_t", 0.0) < 10:
            return
        self._last_resume_t = now

        import keyboard

        was_listening = self.listener.is_running()

        # Tear everything down
        self.snippets.stop()
        if was_listening:
            self.listener.stop()
        try:
            keyboard.unhook_all()   # forces the library to restart its hook thread
        except Exception:
            pass

        # Reinstall everything
        if was_listening:
            self.listener.start()
        self.snippets.start()

        if self.window:
            self.window.update_status("Reconnected after sleep")

    def _start_sleep_detector(self) -> None:
        """Fallback sleep detection via monotonic-clock jump.

        WM_POWERBROADCAST is unreliable when the window is hidden in the tray.
        A sleeping thread that wakes up much later than expected means the OS
        suspended the machine.
        """
        POLL_S  = 10   # check interval
        GRACE_S = 15   # if sleep() runs this many seconds over, assume suspend

        def _monitor() -> None:
            while True:
                t0 = time.monotonic()
                time.sleep(POLL_S)
                if time.monotonic() - t0 > POLL_S + GRACE_S:
                    if self.window:
                        self.window.after(1500, self.on_system_resume)

        threading.Thread(target=_monitor, daemon=True).start()

    # ── hotkey trigger callback (keyboard thread → UI thread) ─────────────────

    def _on_hotkey_triggered(self, hotkey: str, name: str) -> None:
        if self.window:
            msg = f"Triggered:  {hotkey.upper()}  \u2014  {name}"
            self.window.after(0, lambda: self.window.update_status(msg))
