from __future__ import annotations

import ctypes
import ctypes.wintypes as _wt
import sys
from datetime import datetime
from typing import TYPE_CHECKING

import customtkinter as ctk

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
    _PBT_RESUMESUSPEND    = 7   # user-initiated resume
    _PBT_RESUMEAUTOMATIC  = 18  # automatic resume (e.g. scheduled wake)


class MainWindow(ctk.CTk):
    def __init__(self, app: "App") -> None:
        super().__init__()
        self.app = app

        self.title("HotkeyTool")
        self.geometry("1060x620")
        self.minsize(860, 520)

        # Window / taskbar icon — matches the tray icon exactly.
        # Written to a temp .ico so iconbitmap (native Windows API) can consume it.
        # Called via after() so it fires after CTk's own async icon setup.
        self.after(50, self._apply_window_icon)

        self._build()
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.after(200, self._setup_power_hook)

    # ── layout ────────────────────────────────────────────────────────────────

    def _build(self) -> None:
        from ui.bindings_tab  import BindingsTab
        from ui.settings_tab  import SettingsTab
        from ui.schedules_tab import SchedulesTab
        from ui.clipboard_tab import ClipboardTab
        from ui.snippets_tab  import SnippetsTab
        from ui.timer_tab     import TimerTab
        from ui.planner_tab   import PlannerTab

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
            command=lambda: self.app.notes_win.toggle(),
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

        for tab_name in ("Bindings", "Schedules", "Clipboard", "Snippets", "Timer", "Planner", "Settings"):
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

        self._planner_tab   = PlannerTab  (self._tabs.tab("Planner"),   self.app)
        self._planner_tab.pack(fill="both", expand=True)

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

    def _apply_window_icon(self) -> None:
        """Set the title-bar / taskbar icon from assets/hotkeytool.ico.

        Uses LoadImageW + WM_SETICON so Windows picks the correct size frame
        for the current DPI rather than upscaling a small frame.
        """
        import ctypes
        from utils.resource_path import resource_path
        try:
            ico_path = resource_path("assets/hotkeytool.ico")
            if not ico_path.exists():
                return
            path_str = str(ico_path)
            user32 = ctypes.windll.user32
            hwnd = self.winfo_id()
            try:
                dpi = user32.GetDpiForWindow(hwnd)
            except Exception:
                dpi = 96
            big_px   = int(32 * dpi / 96)
            small_px = int(16 * dpi / 96)
            LR_LOADFROMFILE = 0x0010
            IMAGE_ICON      = 1
            WM_SETICON      = 0x0080
            hbig = user32.LoadImageW(
                None, path_str, IMAGE_ICON, big_px, big_px, LR_LOADFROMFILE)
            hsmall = user32.LoadImageW(
                None, path_str, IMAGE_ICON, small_px, small_px, LR_LOADFROMFILE)
            user32.SendMessageW(hwnd, WM_SETICON, 1, hbig)    # ICON_BIG
            user32.SendMessageW(hwnd, WM_SETICON, 0, hsmall)  # ICON_SMALL
        except Exception:
            pass

    def _setup_power_hook(self) -> None:
        """Subclass the native HWND so we receive WM_POWERBROADCAST."""
        if sys.platform != "win32":
            return
        try:
            hwnd = self.winfo_id()
            app  = self.app

            def _proc(hwnd, msg, wparam, lparam):
                if msg == _WM_POWERBROADCAST and wparam in (
                    _PBT_RESUMESUSPEND, _PBT_RESUMEAUTOMATIC
                ):
                    # on_system_resume itself schedules the actual restart 3 s
                    # later, so we just route the wake signal there immediately.
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
