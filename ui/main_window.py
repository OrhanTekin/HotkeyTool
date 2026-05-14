from __future__ import annotations

import ctypes
import ctypes.wintypes as _wt
import sys
from datetime import datetime
from typing import TYPE_CHECKING

import customtkinter as ctk

from ui import theme
from ui.icons import brand_logo, icon as ui_icon
from ui.widgets import GhostButton, HeaderButton, ListenPill, TabBar, Toast

if TYPE_CHECKING:
    from app import App

# ── Windows power-broadcast hook (sleep/wake detection) ───────────────────────
if sys.platform == "win32":
    _u32 = ctypes.windll.user32
    _WNDPROCTYPE = ctypes.WINFUNCTYPE(
        ctypes.c_ssize_t, _wt.HWND, _wt.UINT, _wt.WPARAM, _wt.LPARAM,
    )
    _u32.SetWindowLongPtrW.restype  = ctypes.c_ssize_t
    _u32.SetWindowLongPtrW.argtypes = [_wt.HWND, ctypes.c_int, ctypes.c_ssize_t]
    _u32.CallWindowProcW.restype    = ctypes.c_ssize_t
    _u32.CallWindowProcW.argtypes   = [
        ctypes.c_ssize_t, _wt.HWND, _wt.UINT, _wt.WPARAM, _wt.LPARAM,
    ]
    _GWL_WNDPROC          = -4
    _WM_POWERBROADCAST    = 0x0218
    _PBT_RESUMESUSPEND    = 7
    _PBT_RESUMEAUTOMATIC  = 18


class MainWindow(ctk.CTk):
    def __init__(self, app: "App") -> None:
        super().__init__(fg_color=theme.BG_BASE)
        self.app = app

        self.title("HotkeyTool")
        self.geometry("1100x680")
        self.minsize(880, 560)

        # Pre-arm the Windows WS_EX_LAYERED extended style by setting alpha
        # explicitly once.  Without this, the *first* call in
        # App._reveal_window_smoothly (alpha 0 → deiconify → alpha 1) races
        # the OS adding the layered style, so the very first reveal still
        # shows the bottom-to-top paint flash.
        try:
            self.wm_attributes("-alpha", 1.0)
        except Exception:
            pass

        # toast first so refresh callbacks during build can use it
        self._toast = Toast(self)

        self.after(50, self._apply_window_icon)

        self._build()
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.after(200, self._setup_power_hook)

    # ── public API ────────────────────────────────────────────────────────────

    def toast(self, text: str, *, kind: str = "ok") -> None:
        self._toast.show(text, kind=kind)

    def update_status(self, text: str) -> None:
        # Used by hotkey trigger callback — overwrite the transient message label
        self._status_msg.configure(text=text)
        # auto-clear after 3 s so it doesn't sit forever
        self.after(3000, lambda: self._status_msg.configure(text=""))

    def refresh_bindings(self) -> None:
        self._bindings_tab.refresh()
        self._tab_bar.refresh_counts()
        self._refresh_statusbar_counts()

    def refresh_schedules(self) -> None:
        self._schedules_tab.refresh()
        self._tab_bar.refresh_counts()
        self._refresh_statusbar_counts()

    def refresh_snippets(self) -> None:
        if hasattr(self, "_snippets_tab"):
            self._snippets_tab.refresh()
        self._tab_bar.refresh_counts()
        self._refresh_statusbar_counts()

    def refresh_planner(self) -> None:
        if hasattr(self, "_planner_tab"):
            self._planner_tab.refresh()

    def update_listening_state(self) -> None:
        running = self.app.listener.is_running()
        self._listen_pill.set_listening(running)
        self._set_status_dot(running)

    # ── layout ────────────────────────────────────────────────────────────────

    def _build(self) -> None:
        from ui.bindings_tab  import BindingsTab
        from ui.settings_tab  import SettingsTab
        from ui.schedules_tab import SchedulesTab
        from ui.clipboard_tab import ClipboardTab
        from ui.snippets_tab  import SnippetsTab
        from ui.timer_tab     import TimerTab
        from ui.planner_tab   import PlannerTab

        # ── App header ───────────────────────────────────────────────────────
        header = ctk.CTkFrame(
            self, height=60, corner_radius=0, fg_color=theme.BG_SURFACE,
        )
        header.pack(fill="x", side="top")
        header.pack_propagate(False)

        # brand
        brand = ctk.CTkFrame(header, fg_color="transparent")
        brand.pack(side="left", padx=(18, 0), pady=12)

        logo = ctk.CTkLabel(
            brand, text="", image=brand_logo(30),
            width=30, height=30, fg_color="transparent",
        )
        logo.pack(side="left")

        brand_text = ctk.CTkFrame(brand, fg_color="transparent")
        brand_text.pack(side="left", padx=(10, 0))
        ctk.CTkLabel(
            brand_text, text="HotkeyTool",
            font=theme.font(14, "bold"),
            text_color=theme.TEXT_1, anchor="w",
        ).pack(anchor="w")

        # spacer
        ctk.CTkFrame(header, fg_color="transparent").pack(side="left", expand=True)

        # global listening pill
        self._listen_pill = ListenPill(
            header,
            listening=self.app.listener.is_running(),
            command=self.app.toggle_listening,
            active_count_getter=lambda: sum(1 for b in self.app.config.bindings if b.enabled),
        )
        self._listen_pill.pack(side="left", padx=(0, 12), pady=14)

        # right-side action buttons (design's .icon-btn — transparent + border)
        actions = ctk.CTkFrame(header, fg_color="transparent")
        actions.pack(side="right", padx=(0, 16), pady=14)

        HeaderButton(
            actions, text="Stats", command=self.app.toggle_stats_widget,
            image=ui_icon("chart", 13, theme.TEXT_2),
        ).pack(side="right", padx=(6, 0))

        HeaderButton(
            actions, text="Notes", command=lambda: self.app.notes_win.toggle(),
            image=ui_icon("stickynote", 13, theme.TEXT_2),
        ).pack(side="right")

        # 1-px header underline (drawn on the window so the tab bar sits under it)
        ctk.CTkFrame(self, height=1, fg_color=theme.BORDER_SOFT, corner_radius=0
                     ).pack(side="top", fill="x")

        # ── Tab bar + content stack ─────────────────────────────────────────
        self._tab_bar = TabBar(self)
        self._tab_bar.pack(side="top", fill="both", expand=True)

        cfg = self.app.config
        bindings_page  = self._tab_bar.add("Bindings",  icon="bolt",      count_getter=lambda: len(cfg.bindings))
        schedules_page = self._tab_bar.add("Schedules", icon="calendar",  count_getter=lambda: len(cfg.schedules))
        clipboard_page = self._tab_bar.add("Clipboard", icon="clipboard", count_getter=lambda: len(self.app.clipboard.history))
        snippets_page  = self._tab_bar.add("Snippets",  icon="quote",     count_getter=lambda: len(cfg.snippets))
        timer_page     = self._tab_bar.add("Timer",     icon="timer")
        planner_page   = self._tab_bar.add("Planner",   icon="list",      count_getter=lambda: sum(1 for t in cfg.todos if not t.completed))
        settings_page  = self._tab_bar.add("Settings",  icon="settings")

        self._bindings_tab  = BindingsTab (bindings_page,  self.app)
        self._bindings_tab.pack(fill="both", expand=True)

        self._schedules_tab = SchedulesTab(schedules_page, self.app)
        self._schedules_tab.pack(fill="both", expand=True)

        self._clipboard_tab = ClipboardTab(clipboard_page, self.app)
        self._clipboard_tab.pack(fill="both", expand=True)

        self._snippets_tab  = SnippetsTab (snippets_page,  self.app)
        self._snippets_tab.pack(fill="both", expand=True)

        self._timer_tab     = TimerTab    (timer_page,     self.app)
        self._timer_tab.pack(fill="both", expand=True)

        self._planner_tab   = PlannerTab  (planner_page,   self.app)
        self._planner_tab.pack(fill="both", expand=True)

        self._settings_tab  = SettingsTab (settings_page,  self.app)
        self._settings_tab.pack(fill="both", expand=True)

        # ── Status bar ──────────────────────────────────────────────────────
        sb = ctk.CTkFrame(self, height=28, corner_radius=0,
                          fg_color=theme.BG_TITLEBAR)
        sb.pack(fill="x", side="bottom")
        sb.pack_propagate(False)

        # listener dot + label
        self._status_dot = ctk.CTkLabel(
            sb, text="●", font=theme.font(10),
            text_color=theme.SUCCESS, fg_color="transparent",
        )
        self._status_dot.pack(side="left", padx=(14, 4))
        self._status_label = ctk.CTkLabel(
            sb, text="Listener active",
            font=theme.font(11),
            text_color=theme.TEXT_2, fg_color="transparent",
        )
        self._status_label.pack(side="left")

        ctk.CTkFrame(sb, width=1, height=12, fg_color=theme.BORDER, corner_radius=0
                     ).pack(side="left", padx=12, pady=8)

        self._sb_bindings = ctk.CTkLabel(
            sb, text="0 bindings", font=theme.font(11),
            text_color=theme.TEXT_3, fg_color="transparent",
        )
        self._sb_bindings.pack(side="left")

        ctk.CTkFrame(sb, width=1, height=12, fg_color=theme.BORDER, corner_radius=0
                     ).pack(side="left", padx=12, pady=8)

        self._sb_snippets = ctk.CTkLabel(
            sb, text="0 snippets", font=theme.font(11),
            text_color=theme.TEXT_3, fg_color="transparent",
        )
        self._sb_snippets.pack(side="left")

        ctk.CTkFrame(sb, width=1, height=12, fg_color=theme.BORDER, corner_radius=0
                     ).pack(side="left", padx=12, pady=8)

        self._sb_schedules = ctk.CTkLabel(
            sb, text="0 schedules", font=theme.font(11),
            text_color=theme.TEXT_3, fg_color="transparent",
        )
        self._sb_schedules.pack(side="left")

        # transient hotkey-trigger message
        self._status_msg = ctk.CTkLabel(
            sb, text="", font=theme.font(11),
            text_color=theme.ACCENT, fg_color="transparent",
        )
        self._status_msg.pack(side="left", padx=14)

        # right-aligned mono clock
        self._clock = ctk.CTkLabel(
            sb, text="--:--:--", font=theme.mono(11),
            text_color=theme.TEXT_3, fg_color="transparent",
        )
        self._clock.pack(side="right", padx=14)
        self._tick_clock()

        self._refresh_statusbar_counts()
        self.update_listening_state()

    def _set_status_dot(self, listening: bool) -> None:
        if listening:
            self._status_dot.configure(text_color=theme.SUCCESS)
            self._status_label.configure(text="Listener active", text_color=theme.TEXT_2)
        else:
            self._status_dot.configure(text_color=theme.DANGER)
            self._status_label.configure(text="Listener paused", text_color=theme.TEXT_2)

    def _refresh_statusbar_counts(self) -> None:
        cfg = self.app.config
        self._sb_bindings.configure(text=f"{sum(1 for b in cfg.bindings if b.enabled)} bindings")
        self._sb_snippets.configure(text=f"{sum(1 for s in cfg.snippets if s.enabled)} snippets")
        self._sb_schedules.configure(text=f"{sum(1 for s in cfg.schedules if s.enabled)} schedules")
        # also refresh the listening pill's "active" count
        try:
            self._listen_pill.set_active_count(sum(1 for b in cfg.bindings if b.enabled))
        except Exception:
            pass

    def _tick_clock(self) -> None:
        try:
            self._clock.configure(text=datetime.now().strftime("%H:%M:%S"))
        except Exception:
            return
        self.after(1000, self._tick_clock)

    # ── window icon ──────────────────────────────────────────────────────────
    def _apply_window_icon(self) -> None:
        from utils.resource_path import resource_path
        try:
            ico_path = resource_path("assets/hotkeytool.ico")
            
            # Check if the file actually exists first
            if ico_path.exists():
                # 1. Standard Tkinter method (Handles Title Bar)
                self.iconbitmap(str(ico_path))
                
                # 2. Set the 'Taskbar' icon specifically for Windows
                # This prevents Windows from showing the default 'Python' icon
                if sys.platform == "win32":
                    myappid = 'mycompany.myproduct.subproduct.version' # Arbitrary string
                    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)
            else:
                print(f"Icon not found at: {ico_path}")
        except Exception as e:
            print(f"Failed to set icon: {e}")


    def _setup_power_hook(self) -> None:
        if sys.platform != "win32":
            return
        try:
            hwnd = self.winfo_id()
            app  = self.app

            def _proc(hwnd, msg, wparam, lparam):
                if msg == _WM_POWERBROADCAST and wparam in (
                    _PBT_RESUMESUSPEND, _PBT_RESUMEAUTOMATIC
                ):
                    self.after(0, app.on_system_resume)
                return _u32.CallWindowProcW(
                    self._old_wndproc, hwnd, msg, wparam, lparam
                )

            self._new_wndproc = _WNDPROCTYPE(_proc)
            self._old_wndproc = _u32.SetWindowLongPtrW(
                hwnd, _GWL_WNDPROC, self._new_wndproc
            )
        except Exception:
            pass

    # ── close protocol ────────────────────────────────────────────────────────

    def _on_close(self) -> None:
        if self.app.config.settings.minimize_to_tray_on_close:
            self.withdraw()
        else:
            self.app.quit()
