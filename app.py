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
        register_app_callback("show_window",           self._cb_toggle_window)
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

        self.scheduler.start()
        self.clipboard.start()
        self.snippets.start()

        # Stats monitor
        self.stats_monitor = StatsMonitor(self._on_stats_update)
        self.stats_monitor.start()
        self._start_sleep_detector()
        self._install_pressed_events_watchdog()
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
            self._reveal_window_smoothly()
            self.window.lift()
            self.window.focus_force()

    def _reveal_window_smoothly(self) -> None:
        """Make a withdrawn window appear without the bottom-to-top paint flash.

        After `withdraw()`, Tk discards the rendered surface.  `deiconify()`
        then asks Windows to show the window before any widgets have been
        repainted, so you briefly see a white frame with widgets streaming
        in from the bottom.  Workaround: set the OS-level alpha to 0, then
        deiconify, then force-render via `update_idletasks` while the window
        is invisible, then restore alpha.
        """
        w = self.window
        if not w:
            return
        try:
            w.attributes("-alpha", 0.0)
        except Exception:
            pass
        try:
            w.deiconify()
        except Exception:
            return
        try:
            # update() processes pending paint events too (not just geometry
            # / idle callbacks like update_idletasks), so every widget is
            # actually drawn into the off-screen alpha-0 surface before we
            # unmask it.
            w.update()
        except Exception:
            pass
        try:
            w.attributes("-alpha", 1.0)
        except Exception:
            pass

    def hide_window(self) -> None:
        if self.window:
            self.window.withdraw()

    def _cb_toggle_window(self) -> None:
        """Show-window action: toggle visibility.

        - withdrawn or iconified → show + foreground
        - visible but not foreground → bring to front
        - visible AND foreground   → withdraw (hide to tray)
        """
        if self.window:
            self.window.after(0, self._do_toggle_window)

    def _do_toggle_window(self) -> None:
        if not self.window:
            return
        try:
            state = self.window.state()
        except Exception:
            state = "normal"

        # Hidden (withdrawn) or minimized → show + focus.
        # Visible (regardless of foreground) → withdraw to tray.
        if state in ("withdrawn", "iconic"):
            self._reveal_window_smoothly()
            self.window.lift()
            self.window.focus_force()
        else:
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
        """Cosmetic post-wake notification.

        Actual hotkey-state recovery happens automatically and continuously
        via `_install_pressed_events_watchdog`, which does not depend on
        WM_POWERBROADCAST being delivered.
        """
        now = time.monotonic()
        if now - getattr(self, "_last_resume_t", 0.0) < 5:
            return
        self._last_resume_t = now
        if self.notes_win:
            self.notes_win._first_show = True
        if self.window:
            self.window.update_status("Reconnected after sleep")

    def _install_pressed_events_watchdog(self) -> None:
        """Self-heal `keyboard._pressed_events` on every key event.

        `keyboard.direct_callback` dispatches hotkeys via

            hotkey = tuple(sorted(_pressed_events))
            callback_results = [cb(event) for cb in
                                self.blocking_hotkeys[hotkey]]

        `_pressed_events` is module-level; KEY_DOWN adds, KEY_UP removes.
        When Windows suspends with a key logically "down" — or any KEY_UP
        fails to reach the low-level hook (Ctrl+Win+L lock, modern-standby
        wake, foreground change during a held key) — the scan code stays
        in `_pressed_events` permanently. Every later KEY_DOWN then yields
        a tuple including the stale codes, so the dict lookup never
        matches anything registered. Hotkeys silently stop firing.

        Snippet expansion keeps working because `keyboard.hook()` dispatches
        through the listener's queue + `invoke_handlers`, a path that
        ignores `_pressed_events`. That's also why typing a snippet
        abbreviation "fixes" hotkeys: each real KEY_UP fired during typing
        organically evicts whichever stale scan code happens to match.

        This hook piggybacks on that exact same dispatch path. On every
        event we ask Windows (`GetAsyncKeyState`) whether each entry in
        `_pressed_events` is physically held and pop the ones that aren't.
        No wake detection, no background thread, no retries.
        """
        import keyboard
        import ctypes

        u32 = ctypes.windll.user32

        def _prune(event) -> None:
            # Skip the CURRENT event's scan code.  Between the LL hook firing
            # and the OS finalising the global key state, GetAsyncKeyState may
            # briefly report "not pressed" for the key we just received an
            # event for — evicting it here would break in-progress hotkey
            # combos (Ctrl gets evicted while the user is still building up
            # Ctrl+Alt+X).  All other entries can be checked safely.
            try:
                cur_sc = event.scan_code if event is not None else None
                for sc in list(keyboard._pressed_events):
                    if sc == cur_sc:
                        continue
                    vk = u32.MapVirtualKeyW(abs(sc), 3)  # VSC_TO_VK_EX
                    if vk and not (u32.GetAsyncKeyState(vk) & 0x8000):
                        keyboard._pressed_events.pop(sc, None)
                        keyboard._logically_pressed_keys.pop(sc, None)
            except Exception:
                pass

        try:
            keyboard.hook(_prune, suppress=False)
        except Exception as exc:
            print(f"[HotkeyTool] pressed-events watchdog: {exc}")


    def _start_sleep_detector(self) -> None:
        """Fallback sleep detection via monotonic-clock jump.

        WM_POWERBROADCAST (main_window.py) is the primary wake signal.
        This fallback catches cases where the window is fully hidden/minimized.
        A startup grace period prevents false positives during slow boot.
        """
        POLL_S       = 2
        GRACE_S      = 4
        STARTUP_WAIT = 30

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
