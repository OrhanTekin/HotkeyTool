from __future__ import annotations

import os
import tkinter as tk
import webbrowser
from pathlib import Path
from tkinter import filedialog, messagebox
from typing import TYPE_CHECKING

import customtkinter as ctk

from ui import theme
from ui.icons import brand_logo, icon as ui_icon
from ui.widgets import (
    DangerButton, GhostButton, PrimaryButton, SectionCard, SuccessButton, Switch,
    section_title,
)

if TYPE_CHECKING:
    from app import App


class SettingsTab(ctk.CTkFrame):
    def __init__(self, parent: ctk.CTkBaseClass, app: "App") -> None:
        super().__init__(parent, fg_color=theme.BG_BASE)
        self.app = app
        self._tut_visible = False
        self._build()

    def _build(self) -> None:
        outer = ctk.CTkScrollableFrame(
            self, fg_color=theme.BG_BASE,
            scrollbar_button_color=theme.BG_ELEVATED,
            scrollbar_button_hover_color=theme.BORDER_STRONG,
        )
        outer.pack(fill="both", expand=True, padx=10, pady=4)

        wrap = ctk.CTkFrame(outer, fg_color="transparent", width=760)
        wrap.pack(fill="both", expand=True, padx=4, pady=(8, 40))

        # ── Behaviour ─────────────────────────────────────────────────────────
        section_title(wrap, "Behaviour").pack(fill="x", padx=4, pady=(8, 6))
        beh = SectionCard(wrap)
        beh.pack(fill="x")

        from utils.autostart import is_autostart_enabled
        self._autostart_sw = self._set_row(
            beh, "Start with Windows",
            "Launch HotkeyTool automatically at login.",
            on=is_autostart_enabled(), command=self._toggle_autostart,
        )
        self._set_divider(beh)
        self._tray_sw = self._set_row(
            beh, "Minimize to tray on close",
            "Closing the window keeps the listener running.",
            on=self.app.config.settings.minimize_to_tray_on_close,
            command=self._toggle_tray,
        )
        self._set_divider(beh)
        self._stats_sw = self._set_row(
            beh, "Show Stats widget on startup",
            "Float a small stats panel when the app opens.",
            on=self.app.config.settings.stats_widget_on_startup,
            command=self._toggle_stats_startup,
        )

        # ── Data ──────────────────────────────────────────────────────────────
        section_title(wrap, "Data").pack(fill="x", padx=4, pady=(22, 6))
        data = SectionCard(wrap)
        data.pack(fill="x")

        r = self._set_row_custom(data, "Bindings configuration",
                                 "Backup or restore your bindings as JSON.")
        GhostButton(r, text="Import", small=True, command=self._import,
                    image=ui_icon("upload", 12, theme.TEXT_1), compound="left",
                    ).pack(side="right", padx=(0, 12))
        GhostButton(r, text="Export", small=True, command=self._export,
                    image=ui_icon("download", 12, theme.TEXT_1), compound="left",
                    ).pack(side="right", padx=(0, 4))

        self._set_divider(data)

        from core.config import CONFIG_PATH
        r = self._set_row_custom(data, "Config file", str(CONFIG_PATH), mono_desc=True)
        GhostButton(r, text="Open folder", small=True, command=self._open_config_folder,
                    image=ui_icon("folder", 12, theme.TEXT_1), compound="left",
                    ).pack(side="right", padx=(0, 12))

        # ── Windows Integration ──────────────────────────────────────────────
        section_title(wrap, "Windows Integration").pack(fill="x", padx=4, pady=(22, 6))
        win = SectionCard(wrap)
        win.pack(fill="x")

        r = self._set_row_custom(win, "Desktop shortcut",
                                 "Place a launcher on the desktop.")
        self._shortcut_btn = GhostButton(r, text="", small=True, command=self._toggle_shortcut)
        self._shortcut_btn.pack(side="right", padx=(0, 12))
        self._refresh_shortcut_btn()

        self._set_divider(win)

        r = self._set_row_custom(win, "Explorer context menu",
                                 'Right-click → "Move files to new folder".')
        self._ctxmenu_btn = GhostButton(r, text="", small=True, command=self._toggle_context_menu)
        self._ctxmenu_btn.pack(side="right", padx=(0, 12))
        self._refresh_ctxmenu_btn()

        self._set_divider(win)

        r = self._set_row_custom(win, "Classic context menu (Win 11)",
                                 'Skips the "Show more options" hop.')
        self._classic_btn = GhostButton(r, text="", small=True, command=self._toggle_classic_menu)
        self._classic_btn.pack(side="right", padx=(0, 4))
        GhostButton(r, text="Restart Explorer", small=True, command=self._restart_explorer
                    ).pack(side="right", padx=(0, 12))
        self._refresh_classic_btn()

        # ── Gemini AI ─────────────────────────────────────────────────────────
        section_title(wrap, "Gemini AI · free tier").pack(fill="x", padx=4, pady=(22, 6))
        gemini = SectionCard(wrap)
        gemini.pack(fill="x")

        # API key row
        r = self._set_row_custom(gemini, "API key",
                                 "Used by the 'Gemini: Ask' and 'Gemini: Clipboard' actions.")
        self._gemini_key_var = ctk.StringVar(value=self.app.config.settings.gemini_api_key)
        self._key_entry = ctk.CTkEntry(
            r, textvariable=self._gemini_key_var,
            width=200, height=28, show="•",
            fg_color=theme.BG_INPUT, border_color=theme.BORDER, border_width=1,
            text_color=theme.TEXT_1, font=theme.font(11),
            placeholder_text="paste key…", placeholder_text_color=theme.TEXT_4,
        )
        self._key_entry.pack(side="right", padx=(4, 12))
        self._key_show_btn = GhostButton(r, text="Show", small=True,
                                         command=self._toggle_key_visibility)
        self._key_show_btn.pack(side="right", padx=2)
        PrimaryButton(r, text="Save", small=True, command=self._save_gemini_key
                      ).pack(side="right", padx=2)

        self._set_divider(gemini)

        # API key URL + tutorial
        info_row = ctk.CTkFrame(gemini, fg_color="transparent")
        info_row.pack(fill="x", padx=14, pady=(10, 6))
        ctk.CTkLabel(info_row, text="Free key (no credit card):",
                     font=theme.font(11), text_color=theme.TEXT_3,
                     fg_color="transparent",
                     ).pack(side="left")
        ctk.CTkButton(
            info_row, text="aistudio.google.com/apikey",
            font=theme.font(11),
            fg_color="transparent", hover_color=theme.BG_HOVER,
            text_color=theme.ACCENT,
            width=10, height=22, cursor="hand2",
            command=lambda: webbrowser.open("https://aistudio.google.com/apikey"),
        ).pack(side="left", padx=4)
        GhostButton(info_row, text="Copy URL", small=True,
                    command=lambda: self._copy_text("https://aistudio.google.com/apikey")
                    ).pack(side="left", padx=2)

        self._tut_btn = ctk.CTkButton(
            gemini, text="▶  Setup Tutorial",
            font=theme.font(11),
            fg_color="transparent", hover_color=theme.BG_HOVER,
            text_color=theme.TEXT_3, anchor="w",
            command=self._toggle_tutorial,
        )
        self._tut_btn.pack(fill="x", padx=14, pady=(0, 4))

        self._tut_frame = ctk.CTkFrame(
            gemini, fg_color=theme.BG_BASE, corner_radius=6,
            border_color=theme.BORDER_SOFT, border_width=1,
        )
        ctk.CTkLabel(
            self._tut_frame,
            text=(
                "1.  Click 'Create API Key'\n"
                "2.  Select 'Default Gemini Project' → Create\n"
                "3.  Copy the API key and paste it in the field above"
            ),
            font=theme.font(11),
            text_color=theme.TEXT_2, fg_color="transparent",
            justify="left", anchor="w",
        ).pack(padx=14, pady=8, fill="x")

        ctk.CTkLabel(
            gemini,
            text="Actions: 'Gemini: Clipboard' — image/text → Gemini → clipboard\n"
                 "         'Gemini: Ask'       — open floating chat window",
            font=theme.font(11), text_color=theme.TEXT_3,
            fg_color="transparent",
            justify="left", anchor="w",
        ).pack(padx=14, pady=(2, 12), fill="x")

        # ── About ─────────────────────────────────────────────────────────────
        section_title(wrap, "About").pack(fill="x", padx=4, pady=(22, 6))
        about = SectionCard(wrap)
        about.pack(fill="x")

        about_row = ctk.CTkFrame(about, fg_color="transparent")
        about_row.pack(fill="x", padx=14, pady=14)

        # Same gradient brand logo as the app header (top-left), at 40px.
        ctk.CTkLabel(
            about_row, text="", image=brand_logo(40),
            width=40, height=40, fg_color="transparent",
        ).pack(side="left", padx=(0, 12))

        text = ctk.CTkFrame(about_row, fg_color="transparent")
        text.pack(side="left", anchor="w")
        ctk.CTkLabel(
            text, text="HotkeyTool · v1.0",
            font=theme.font(13, "bold"),
            text_color=theme.TEXT_1, fg_color="transparent", anchor="w",
        ).pack(anchor="w")
        ctk.CTkLabel(
            text, text="Global hotkey manager and productivity suite for Windows 11.",
            font=theme.font(11), text_color=theme.TEXT_3,
            fg_color="transparent", anchor="w",
        ).pack(anchor="w")

    # ── row helpers ───────────────────────────────────────────────────────────

    def _set_row(self, parent, label: str, desc: str, *, on: bool,
                 command) -> Switch:
        row = ctk.CTkFrame(parent, fg_color="transparent", height=58)
        row.pack(fill="x", padx=14, pady=2)
        row.pack_propagate(False)
        text = ctk.CTkFrame(row, fg_color="transparent")
        text.pack(side="left", fill="x", expand=True, pady=10)
        ctk.CTkLabel(
            text, text=label, font=theme.font(13, "bold"),
            text_color=theme.TEXT_1, fg_color="transparent", anchor="w",
        ).pack(anchor="w")
        ctk.CTkLabel(
            text, text=desc, font=theme.font(11),
            text_color=theme.TEXT_3, fg_color="transparent", anchor="w",
        ).pack(anchor="w")
        sw = Switch(row, on=on, command=lambda v: command(v))
        sw.pack(side="right", pady=10)
        return sw

    def _set_row_custom(self, parent, label: str, desc: str, *,
                        mono_desc: bool = False) -> ctk.CTkFrame:
        row = ctk.CTkFrame(parent, fg_color="transparent", height=58)
        row.pack(fill="x", padx=14, pady=2)
        row.pack_propagate(False)
        text = ctk.CTkFrame(row, fg_color="transparent")
        text.pack(side="left", fill="x", expand=True, pady=10)
        ctk.CTkLabel(
            text, text=label, font=theme.font(13, "bold"),
            text_color=theme.TEXT_1, fg_color="transparent", anchor="w",
        ).pack(anchor="w")
        ctk.CTkLabel(
            text, text=desc,
            font=theme.mono(11) if mono_desc else theme.font(11),
            text_color=theme.TEXT_3, fg_color="transparent", anchor="w",
        ).pack(anchor="w")
        return row

    def _set_divider(self, parent) -> None:
        ctk.CTkFrame(parent, height=1, fg_color=theme.BORDER_SOFT, corner_radius=0
                     ).pack(fill="x", padx=4)

    # ── callbacks ─────────────────────────────────────────────────────────────

    def _toggle_autostart(self, on: bool) -> None:
        from utils.autostart import enable_autostart, disable_autostart
        if on:
            enable_autostart()
        else:
            disable_autostart()
        self.app.config.settings.autostart = on
        from core.config import save_config
        save_config(self.app.config)
        if self.app.window:
            self.app.window.toast("Setting saved")

    def _toggle_tray(self, on: bool) -> None:
        self.app.config.settings.minimize_to_tray_on_close = on
        from core.config import save_config
        save_config(self.app.config)
        if self.app.window:
            self.app.window.toast("Setting saved")

    def _toggle_stats_startup(self, on: bool) -> None:
        self.app.config.settings.stats_widget_on_startup = on
        from core.config import save_config
        save_config(self.app.config)
        if self.app.window:
            self.app.window.toast("Setting saved")

    def _refresh_shortcut_btn(self) -> None:
        from setup import shortcut_exists
        if shortcut_exists():
            self._shortcut_btn.configure(text="Remove shortcut")
        else:
            self._shortcut_btn.configure(text="Create shortcut")

    def _refresh_ctxmenu_btn(self) -> None:
        from setup import context_menu_registered
        if context_menu_registered():
            self._ctxmenu_btn.configure(text="Unregister")
        else:
            self._ctxmenu_btn.configure(text="Register")

    def _refresh_classic_btn(self) -> None:
        from setup import classic_context_menu_enabled
        if classic_context_menu_enabled():
            self._classic_btn.configure(text="Disable")
        else:
            self._classic_btn.configure(text="Enable")

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
            "Click 'Restart Explorer' to apply the change immediately, "
            "or sign out and back in.",
        )

    def _restart_explorer(self) -> None:
        if messagebox.askyesno(
            "Restart Explorer",
            "This will briefly close and reopen Windows Explorer "
            "(all open folder windows will close). Continue?",
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
        if self.app.window:
            self.app.window.toast("API key saved")

    def _toggle_key_visibility(self) -> None:
        if self._key_entry.cget("show") == "•":
            self._key_entry.configure(show="")
            self._key_show_btn.configure(text="Hide")
        else:
            self._key_entry.configure(show="•")
            self._key_show_btn.configure(text="Show")

    def _toggle_tutorial(self) -> None:
        if self._tut_visible:
            self._tut_frame.pack_forget()
            self._tut_btn.configure(text="▶  Setup Tutorial")
            self._tut_visible = False
        else:
            self._tut_frame.pack(fill="x", padx=14, pady=(0, 8))
            self._tut_btn.configure(text="▼  Setup Tutorial")
            self._tut_visible = True

    def _copy_text(self, text: str) -> None:
        self.clipboard_clear()
        self.clipboard_append(text)
        if self.app.window:
            self.app.window.toast("Copied")

    def _open_config_folder(self) -> None:
        from core.config import CONFIG_PATH
        os.startfile(str(CONFIG_PATH.parent))

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
        if self.app.window:
            self.app.window.toast("Bindings exported")

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
                self.app.window.toast(f"Imported {len(new_cfg.bindings)} bindings")
        except Exception as exc:
            messagebox.showerror("Import Error", f"Failed to import:\n{exc}")
