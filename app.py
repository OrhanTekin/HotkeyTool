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
        register_app_callback("toggle_stats_widget",   self._cb_toggle_stats)
        register_app_callback("show_notes_window",     self._cb_show_notes)
        register_app_callback("show_window",           self.show_window)
        register_app_callback("show_transform_picker", self._cb_show_transform_picker)
        register_app_callback("get_gemini_key",        lambda: self.config.settings.gemini_api_key)
        register_app_callback("gemini_ask",            self._cb_gemini_ask)
        register_app_callback("show_api_key_missing",  self._cb_show_api_key_missing)

    # ── lifecycle ─────────────────────────────────────────────────────────────

    def run(self) -> None:
        from ui.main_window import MainWindow
        from ui.tray import TrayIcon
        from utils.fonts import load_app_fonts

        load_app_fonts()
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")

        # One-time migration: move notes from config.json to individual .txt files
        if self.config.notes:
            from core.notes_manager import migrate_from_config
            migrate_from_config([n.to_dict() for n in self.config.notes])

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
            # Boot-time recovery: SetWindowsHookEx can fail before Windows input subsystem is ready
            self.window.after(15000, self._do_resume_restart)

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

    # ── gemini ask window ─────────────────────────────────────────────────────

    def _cb_gemini_ask(self) -> None:
        if self.window:
            self.window.after(0, self._open_gemini_ask)

    def _open_gemini_ask(self) -> None:
        from ui.gemini_ask_window import GeminiAskWindow
        GeminiAskWindow(self)

    def _cb_show_api_key_missing(self) -> None:
        """Open the themed 'Gemini API key required' popup on the UI thread.
        Safe to invoke from action_runner's daemon thread."""
        from ui.transform_picker import show_api_key_missing
        show_api_key_missing(self)

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
        """Schedule keyboard-listener restart attempts after wake.

        Replaces keyboard._listener with a brand-new instance so the listening
        thread is respawned and SetWindowsHookEx() runs with a fresh handle.
        """
        now = time.monotonic()
        if now - getattr(self, "_last_resume_t", 0.0) < 5:
            return
        self._last_resume_t = now

        if self.window:
            for delay in (3000, 7000, 15000, 30000):
                self.window.after(delay, self._do_resume_restart)

    
    def _do_resume_restart(self) -> None:
        """Replace keyboard._listener with a fresh instance and re-register.

        Safe to call multiple times (staggered attempts after wake).

        The old code used self.listener.is_running() for was_listening.
        The 3 s attempt calls listener.stop() → _running=False, so every
        later attempt (7 s, 15 s, 30 s) saw was_listening=False and silently
        skipped re-registration.  If 3 s failed because Windows wasn't ready
        yet, hotkeys were never restored.  Fix: use self.config.listening
        (user's saved intent) which is never touched by runtime stop/start.
        """
        import keyboard

        # User's saved intent — never modified by runtime stop/start.
        should_listen = self.config.listening

        # 1. Tear down both wrappers unconditionally (safe if already stopped).
        try:
            self.snippets.stop()
        except Exception:
            pass
        try:
            self.listener.stop()
        except Exception:
            pass

        # 2. Replace keyboard._listener with a completely fresh instance.
        #    After sleep/wake the WH_KEYBOARD_LL hook handle is invalidated by
        #    Windows but the library thread stays alive, so start_if_necessary()
        #    is a no-op (sees listening=True and returns immediately).
        #    A brand-new instance starts with listening=False, so the first
        #    add_hotkey() call triggers start_if_necessary() → new thread →
        #    fresh SetWindowsHookEx().
        try:
            keyboard._listener = type(keyboard._listener)()
        except Exception as exc:
            print(f"[HotkeyTool] resume: listener replace: {exc}")

        # 3. Re-register everything against the fresh listener.
        try:
            if should_listen:
                self.listener.start()
        except Exception as exc:
            print(f"[HotkeyTool] resume: listener.start: {exc}")
        try:
            self.snippets.start()
        except Exception as exc:
            print(f"[HotkeyTool] resume: snippets.start: {exc}")

        # 4. Reset notes window focus state.
        if self.notes_win:
            self.notes_win._first_show = True

        if self.window:
            self.window.update_status("Reconnected after sleep")


    def _start_sleep_detector(self) -> None:
        """Fallback sleep detection via monotonic-clock jump.

        WM_POWERBROADCAST (main_window.py) is the primary wake signal.
        This fallback catches cases where the window is fully hidden/minimized.
        A startup grace period prevents false positives during slow boot.
        """
        POLL_S       = 2    # check interval
        GRACE_S      = 4    # extra seconds before assuming suspend (threshold = POLL_S + GRACE_S = 6 s)
        STARTUP_WAIT = 30   # skip checks for this long after launch to avoid boot false-positives

        def _monitor() -> None:
            time.sleep(STARTUP_WAIT)
            while True:
                t0 = time.monotonic()
                time.sleep(POLL_S)
                if time.monotonic() - t0 > POLL_S + GRACE_S:
                    if self.window:
                        self.window.after(0, self.on_system_resume)

        threading.Thread(target=_monitor, daemon=True).start()

    # ── hotkey trigger callback (keyboard thread → UI thread) ─────────────────

    def _on_hotkey_triggered(self, hotkey: str, name: str) -> None:
        if self.window:
            msg = f"Triggered:  {hotkey.upper()}  \u2014  {name}"
            self.window.after(0, lambda: self.window.update_status(msg))
