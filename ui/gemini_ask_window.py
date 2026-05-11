"""
Floating 'Ask Gemini' window — opened by the gemini_ask hotkey action.
"""
from __future__ import annotations

import threading
import tkinter as tk
from typing import TYPE_CHECKING

import customtkinter as ctk

from ui import theme
from ui.widgets import GhostButton, PrimaryButton

if TYPE_CHECKING:
    from app import App


class GeminiAskWindow(ctk.CTkToplevel):
    def __init__(self, app: "App") -> None:
        super().__init__(fg_color=theme.BG_BASE)
        self._app = app
        self.title("Ask Gemini")
        self.geometry("620x460")
        self.minsize(460, 320)
        self.wm_attributes("-topmost", True)
        self.configure(fg_color=theme.BG_BASE)
        self._build()
        from utils.resource_path import apply_window_icon
        self.after(200, lambda: apply_window_icon(self))
        self.lift()
        self.after(80, self._question_entry.focus_set)

    # ── layout ────────────────────────────────────────────────────────────────

    def _build(self) -> None:
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        # ── Header strip ──
        head = ctk.CTkFrame(self, fg_color=theme.BG_SURFACE,
                            corner_radius=0, height=58)
        head.grid(row=0, column=0, sticky="ew")
        head.grid_columnconfigure(0, weight=1)
        head.grid_propagate(False)

        title_col = ctk.CTkFrame(head, fg_color="transparent")
        title_col.grid(row=0, column=0, sticky="w", padx=18, pady=10)
        ctk.CTkLabel(
            title_col, text="Ask Gemini",
            font=theme.font(14, "bold"), text_color=theme.TEXT_1,
            fg_color="transparent",
        ).pack(anchor="w")
        ctk.CTkLabel(
            title_col, text="Ask anything — responses are returned inline.",
            font=theme.font(11), text_color=theme.TEXT_3,
            fg_color="transparent",
        ).pack(anchor="w")

        # 1-px divider under header (matches main window)
        ctk.CTkFrame(self, height=1, fg_color=theme.BORDER_SOFT,
                     corner_radius=0).grid(row=0, column=0, sticky="sew")

        # ── Body ──
        body = ctk.CTkFrame(self, fg_color=theme.BG_BASE, corner_radius=0)
        body.grid(row=1, column=0, sticky="nsew")
        body.grid_columnconfigure(0, weight=1)
        body.grid_rowconfigure(1, weight=1)

        # Question row
        q_row = ctk.CTkFrame(body, fg_color="transparent")
        q_row.grid(row=0, column=0, sticky="ew", padx=18, pady=(14, 8))
        q_row.columnconfigure(0, weight=1)

        self._question_var = ctk.StringVar()
        self._question_entry = ctk.CTkEntry(
            q_row, textvariable=self._question_var,
            placeholder_text="Ask Gemini anything…",
            height=36,
            fg_color=theme.BG_INPUT,
            border_color=theme.BORDER, border_width=1,
            text_color=theme.TEXT_1,
            placeholder_text_color=theme.TEXT_3,
            font=theme.font(13),
        )
        self._question_entry.grid(row=0, column=0, sticky="ew", padx=(0, 8))
        self._question_entry.bind("<Return>", lambda _: self._ask())

        self._ask_btn = PrimaryButton(q_row, text="Ask", command=self._ask,
                                      width=88, height=36)
        self._ask_btn.grid(row=0, column=1)

        # Result area (raw Tk so we can theme it precisely)
        result_wrap = ctk.CTkFrame(
            body, fg_color=theme.BG_SURFACE,
            border_color=theme.BORDER, border_width=1,
            corner_radius=theme.RADIUS,
        )
        result_wrap.grid(row=1, column=0, sticky="nsew", padx=18, pady=(0, 8))
        result_wrap.grid_columnconfigure(0, weight=1)
        result_wrap.grid_rowconfigure(0, weight=1)

        self._result = tk.Text(
            result_wrap, wrap="word",
            bg=theme.BG_SURFACE, fg=theme.TEXT_1,
            insertbackground=theme.ACCENT,
            selectbackground=theme.ACCENT_BG_2,
            selectforeground=theme.TEXT_1,
            font=(theme.mono_family(), 11),
            relief="flat", borderwidth=0,
            padx=14, pady=12,
            state="disabled",
        )
        self._result.grid(row=0, column=0, sticky="nsew", padx=1, pady=1)

        # Bottom bar
        bar = ctk.CTkFrame(body, fg_color="transparent")
        bar.grid(row=2, column=0, sticky="ew", padx=18, pady=(0, 14))

        self._status = ctk.CTkLabel(
            bar, text="", font=theme.font(11),
            text_color=theme.TEXT_3, fg_color="transparent",
            anchor="w",
        )
        self._status.pack(side="left")

        GhostButton(bar, text="Copy result", small=True,
                    command=self._copy_result).pack(side="right", padx=(6, 0))
        GhostButton(bar, text="Clear", small=True,
                    command=self._clear).pack(side="right")

    # ── actions ───────────────────────────────────────────────────────────────

    def _ask(self) -> None:
        question = self._question_var.get().strip()
        if not question:
            return
        key = self._app.config.settings.gemini_api_key
        if not key:
            self._set_result("[No API key] Add your free Gemini API key in Settings → Gemini.")
            return
        self._ask_btn.configure(state="disabled", text="…")
        self._status.configure(text="Asking Gemini…", text_color=theme.TEXT_3)
        self._set_result("")
        threading.Thread(target=self._run, args=(key, question), daemon=True).start()

    def _run(self, key: str, question: str) -> None:
        try:
            from core.gemini import call_gemini
            result = call_gemini(key, question)
            self.after(0, lambda: self._set_result(result))
            self.after(0, lambda: self._status.configure(
                text="Done.", text_color=theme.SUCCESS))
        except Exception as exc:
            self.after(0, lambda: self._set_result(f"[Error] {exc}"))
            self.after(0, lambda: self._status.configure(
                text="Error.", text_color=theme.DANGER))
        finally:
            self.after(0, lambda: self._ask_btn.configure(state="normal", text="Ask"))

    def _set_result(self, text: str) -> None:
        self._result.configure(state="normal")
        self._result.delete("1.0", "end")
        if text:
            self._result.insert("1.0", text)
        self._result.configure(state="disabled")

    def _copy_result(self) -> None:
        text = self._result.get("1.0", "end-1c").strip()
        if not text:
            return
        from core.action_runner import _write_clipboard_text
        _write_clipboard_text(text)
        self._status.configure(text="Copied.", text_color=theme.SUCCESS)

    def _clear(self) -> None:
        self._question_var.set("")
        self._set_result("")
        self._status.configure(text="", text_color=theme.TEXT_3)
        self._question_entry.focus_set()
