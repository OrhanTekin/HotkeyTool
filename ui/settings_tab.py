from __future__ import annotations

from pathlib import Path
from tkinter import filedialog, messagebox
from typing import TYPE_CHECKING

import customtkinter as ctk

if TYPE_CHECKING:
    from app import App


class SettingsTab(ctk.CTkFrame):
    def __init__(self, parent: ctk.CTkBaseClass, app: "App") -> None:
        super().__init__(parent, fg_color="transparent")
        self.app = app
        self._build()

    def _build(self) -> None:
        wrap = ctk.CTkScrollableFrame(self, fg_color="transparent")
        wrap.pack(fill="both", expand=True, padx=36, pady=16)

        # ── Behaviour section ──────────────────────────────────────────────
        self._section(wrap, "Behaviour")

        r1 = self._row(wrap)
        ctk.CTkLabel(r1, text="Start with Windows",
                     font=ctk.CTkFont(size=13)).pack(side="left")
        from utils.autostart import is_autostart_enabled
        self._autostart_var = ctk.BooleanVar(value=is_autostart_enabled())
        ctk.CTkSwitch(
            r1, text="",
            variable=self._autostart_var, onvalue=True, offvalue=False,
            command=self._toggle_autostart,
        ).pack(side="right")

        r2 = self._row(wrap)
        ctk.CTkLabel(r2, text="Minimize to tray on close",
                     font=ctk.CTkFont(size=13)).pack(side="left")
        self._tray_var = ctk.BooleanVar(
            value=self.app.config.settings.minimize_to_tray_on_close
        )
        ctk.CTkSwitch(
            r2, text="",
            variable=self._tray_var, onvalue=True, offvalue=False,
            command=self._toggle_tray,
        ).pack(side="right")

        r_stats = self._row(wrap)
        ctk.CTkLabel(r_stats, text="Show Stats Widget on startup",
                     font=ctk.CTkFont(size=13)).pack(side="left")
        self._stats_var = ctk.BooleanVar(
            value=self.app.config.settings.stats_widget_on_startup
        )
        ctk.CTkSwitch(
            r_stats, text="",
            variable=self._stats_var, onvalue=True, offvalue=False,
            command=self._toggle_stats_startup,
        ).pack(side="right")

        r_theme = self._row(wrap)
        ctk.CTkLabel(r_theme, text="UI Theme",
                     font=ctk.CTkFont(size=13)).pack(side="left")
        cur_theme = self.app.config.settings.theme.capitalize()
        if cur_theme not in ("Dark", "Light", "System"):
            cur_theme = "Dark"
        self._theme_seg = ctk.CTkSegmentedButton(
            r_theme,
            values=["Dark", "Light", "System"],
            command=self._change_theme,
            width=220, height=30,
        )
        self._theme_seg.set(cur_theme)
        self._theme_seg.pack(side="right")

        self._divider(wrap)

        # ── Data section ───────────────────────────────────────────────────
        self._section(wrap, "Data")

        r3 = self._row(wrap)
        ctk.CTkLabel(r3, text="Bindings JSON",
                     font=ctk.CTkFont(size=13)).pack(side="left")
        ctk.CTkButton(
            r3, text="Export", width=100, height=30,
            command=self._export,
        ).pack(side="right", padx=(4, 0))
        ctk.CTkButton(
            r3, text="Import", width=100, height=30,
            fg_color=("#1e2a3a", "#1e2a3a"), hover_color=("#2a3a4a", "#2a3a4a"),
            command=self._import,
        ).pack(side="right", padx=(0, 4))

        # Config path info
        from core.config import CONFIG_PATH
        info = ctk.CTkFrame(wrap, fg_color=("#0f0f22", "#0f0f22"), corner_radius=6)
        info.pack(fill="x", pady=(6, 0))
        ctk.CTkLabel(
            info, text=f"Config stored at:  {CONFIG_PATH}",
            font=ctk.CTkFont(size=10),
            text_color=("#555577", "#555577"),
            anchor="w",
        ).pack(padx=10, pady=6, fill="x")

        self._divider(wrap)

        # ── Windows Integration section ────────────────────────────────────
        self._section(wrap, "Windows Integration")

        r4 = self._row(wrap)
        ctk.CTkLabel(r4, text="Desktop shortcut",
                     font=ctk.CTkFont(size=13)).pack(side="left")
        self._shortcut_btn = ctk.CTkButton(
            r4, text="", width=130, height=30,
            command=self._toggle_shortcut,
        )
        self._shortcut_btn.pack(side="right")
        self._refresh_shortcut_btn()

        r5 = self._row(wrap)
        ctk.CTkLabel(r5,
                     text='Explorer: "Dateien in neuen Ordner bewegen"',
                     font=ctk.CTkFont(size=13)).pack(side="left")
        self._ctxmenu_btn = ctk.CTkButton(
            r5, text="", width=130, height=30,
            command=self._toggle_context_menu,
        )
        self._ctxmenu_btn.pack(side="right")
        self._refresh_ctxmenu_btn()

        r6 = self._row(wrap)
        ctk.CTkLabel(r6,
                     text="Windows 11 classic context menu",
                     font=ctk.CTkFont(size=13)).pack(side="left")
        self._restart_btn = ctk.CTkButton(
            r6, text="Restart Explorer", width=130, height=30,
            fg_color=("#1e2a3a", "#1e2a3a"), hover_color=("#2a3a4a", "#2a3a4a"),
            command=self._restart_explorer,
        )
        self._restart_btn.pack(side="right", padx=(4, 0))
        self._classic_btn = ctk.CTkButton(
            r6, text="", width=130, height=30,
            command=self._toggle_classic_menu,
        )
        self._classic_btn.pack(side="right", padx=(0, 4))
        self._refresh_classic_btn()

        # Info label
        info_lbl = ctk.CTkLabel(
            wrap,
            text=(
                "Windows 11 hides custom entries behind \"Show more options\".\n"
                "Enabling the classic menu makes the entry visible immediately on right-click."
            ),
            font=ctk.CTkFont(size=10),
            text_color=("#555577", "#555577"),
            justify="left",
            anchor="w",
        )
        info_lbl.pack(fill="x", pady=(0, 4))

        self._divider(wrap)

        # ── Gemini AI section ──────────────────────────────────────────────
        self._section(wrap, "Gemini AI  (free tier)")

        key_row = self._row(wrap)
        ctk.CTkLabel(key_row, text="API Key",
                     font=ctk.CTkFont(size=13)).pack(side="left")
        self._gemini_key_var = ctk.StringVar(
            value=self.app.config.settings.gemini_api_key)
        ctk.CTkEntry(
            key_row, textvariable=self._gemini_key_var,
            width=260, height=30, show="•",
            placeholder_text="Paste your free key here…",
        ).pack(side="right", padx=(0, 6))
        ctk.CTkButton(
            key_row, text="Save", width=60, height=30,
            command=self._save_gemini_key,
        ).pack(side="right")

        info_row = ctk.CTkFrame(wrap, fg_color=("#0f0f22", "#0f0f22"), corner_radius=6)
        info_row.pack(fill="x", pady=(2, 0))
        ctk.CTkLabel(
            info_row,
            text="Free key (no credit card): aistudio.google.com/apikey\n"
                 "Actions: 'Gemini: Clipboard' — image/text → Gemini → clipboard\n"
                 "         'Gemini: Ask'       — open floating chat window",
            font=ctk.CTkFont(size=10),
            text_color=("#555577", "#555577"),
            justify="left", anchor="w",
        ).pack(padx=10, pady=6, fill="x")

        self._divider(wrap)

        # ── About section ──────────────────────────────────────────────────
        self._section(wrap, "About")
        about = ctk.CTkFrame(wrap, fg_color=("#0f0f22", "#0f0f22"), corner_radius=8)
        about.pack(fill="x")
        ctk.CTkLabel(
            about,
            text="HotkeyTool  v1.0\nGlobal hotkey manager for Windows 11",
            font=ctk.CTkFont(size=12),
            text_color=("#777799", "#777799"),
            justify="left",
        ).pack(padx=14, pady=10, anchor="w")

    # ── helpers ───────────────────────────────────────────────────────────────

    def _section(self, parent: ctk.CTkBaseClass, title: str) -> None:
        ctk.CTkLabel(
            parent, text=title,
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color=("#99aacc", "#99aacc"),
            anchor="w",
        ).pack(fill="x", pady=(6, 2))

    def _row(self, parent: ctk.CTkBaseClass) -> ctk.CTkFrame:
        row = ctk.CTkFrame(parent, fg_color="transparent", height=42)
        row.pack(fill="x", pady=2)
        row.pack_propagate(False)
        return row

    def _divider(self, parent: ctk.CTkBaseClass) -> None:
        ctk.CTkFrame(parent, height=1,
                     fg_color=("#2a2a44", "#2a2a44")).pack(fill="x", pady=14)

    # ── callbacks ─────────────────────────────────────────────────────────────

    def _toggle_autostart(self) -> None:
        from utils.autostart import enable_autostart, disable_autostart
        if self._autostart_var.get():
            enable_autostart()
        else:
            disable_autostart()
        self.app.config.settings.autostart = self._autostart_var.get()
        from core.config import save_config
        save_config(self.app.config)

    def _toggle_tray(self) -> None:
        self.app.config.settings.minimize_to_tray_on_close = self._tray_var.get()
        from core.config import save_config
        save_config(self.app.config)

    def _toggle_stats_startup(self) -> None:
        self.app.config.settings.stats_widget_on_startup = self._stats_var.get()
        from core.config import save_config
        save_config(self.app.config)

    def _change_theme(self, value: str) -> None:
        import customtkinter as ctk
        theme = value.lower()
        ctk.set_appearance_mode(theme)
        self.app.config.settings.theme = theme
        from core.config import save_config
        save_config(self.app.config)

    def _refresh_shortcut_btn(self) -> None:
        from setup import shortcut_exists
        if shortcut_exists():
            self._shortcut_btn.configure(
                text="Remove shortcut",
                fg_color=("#5c1a1a", "#5c1a1a"),
                hover_color=("#7a2222", "#7a2222"),
            )
        else:
            self._shortcut_btn.configure(
                text="Create shortcut",
                fg_color=("#163a22", "#163a22"),
                hover_color=("#1e4a2a", "#1e4a2a"),
            )

    def _refresh_ctxmenu_btn(self) -> None:
        from setup import context_menu_registered
        if context_menu_registered():
            self._ctxmenu_btn.configure(
                text="Unregister",
                fg_color=("#5c1a1a", "#5c1a1a"),
                hover_color=("#7a2222", "#7a2222"),
            )
        else:
            self._ctxmenu_btn.configure(
                text="Register",
                fg_color=("#163a22", "#163a22"),
                hover_color=("#1e4a2a", "#1e4a2a"),
            )

    def _toggle_shortcut(self) -> None:
        from setup import (
            shortcut_exists, create_desktop_shortcut,
            remove_desktop_shortcut, generate_icon, ICON_PATH,
        )
        try:
            if shortcut_exists():
                remove_desktop_shortcut()
            else:
                if not ICON_PATH.exists():
                    generate_icon()
                create_desktop_shortcut()
        except Exception as exc:
            messagebox.showerror("Error", str(exc))
        self._refresh_shortcut_btn()

    def _refresh_classic_btn(self) -> None:
        from setup import classic_context_menu_enabled
        if classic_context_menu_enabled():
            self._classic_btn.configure(
                text="Disable (Win 11 style)",
                fg_color=("#5c1a1a", "#5c1a1a"),
                hover_color=("#7a2222", "#7a2222"),
            )
        else:
            self._classic_btn.configure(
                text="Enable (recommended)",
                fg_color=("#163a22", "#163a22"),
                hover_color=("#1e4a2a", "#1e4a2a"),
            )

    def _toggle_classic_menu(self) -> None:
        from setup import (classic_context_menu_enabled,
                           enable_classic_context_menu,
                           disable_classic_context_menu)
        try:
            if classic_context_menu_enabled():
                disable_classic_context_menu()
            else:
                enable_classic_context_menu()
        except Exception as exc:
            messagebox.showerror("Error", str(exc))
        self._refresh_classic_btn()
        messagebox.showinfo(
            "Context Menu",
            "Click 'Restart Explorer' to apply the change immediately,\n"
            "or sign out and back in.",
        )

    def _restart_explorer(self) -> None:
        if messagebox.askyesno(
            "Restart Explorer",
            "This will briefly close and reopen Windows Explorer\n"
            "(all open folder windows will close).\n\nContinue?",
        ):
            from setup import restart_explorer
            restart_explorer()

    def _toggle_context_menu(self) -> None:
        from setup import (
            context_menu_registered, register_context_menu,
            unregister_context_menu, generate_icon, ICON_PATH,
        )
        try:
            if context_menu_registered():
                unregister_context_menu()
            else:
                if not ICON_PATH.exists():
                    generate_icon()
                register_context_menu()
        except Exception as exc:
            messagebox.showerror("Error", str(exc))
        self._refresh_ctxmenu_btn()

    def _save_gemini_key(self) -> None:
        self.app.config.settings.gemini_api_key = self._gemini_key_var.get().strip()
        from core.config import save_config
        save_config(self.app.config)

    def _export(self) -> None:
        path = filedialog.asksaveasfilename(
            defaultextension=".json",
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")],
            initialfile="hotkeytool_bindings.json",
        )
        if not path:
            return
        from core.config import export_config
        export_config(self.app.config, Path(path))
        messagebox.showinfo("Export", f"Bindings exported to:\n{path}")

    def _import(self) -> None:
        path = filedialog.askopenfilename(
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")]
        )
        if not path:
            return
        try:
            from core.config import import_config, save_config
            new_cfg = import_config(Path(path))
            self.app.config.bindings = new_cfg.bindings
            save_config(self.app.config)
            self.app.listener.reload()
            if self.app.window:
                self.app.window.refresh_bindings()
            messagebox.showinfo("Import",
                                f"Imported {len(new_cfg.bindings)} binding(s) successfully.")
        except Exception as exc:
            messagebox.showerror("Import Error", f"Failed to import:\n{exc}")
