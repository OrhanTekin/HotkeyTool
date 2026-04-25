"""
Floating 'Ask Gemini' window — opened by the gemini_ask hotkey action.
"""
from __future__ import annotations

import threading
from typing import TYPE_CHECKING

import customtkinter as ctk

if TYPE_CHECKING:
    from app import App


class GeminiAskWindow(ctk.CTkToplevel):
    def __init__(self, app: "App") -> None:
        super().__init__()
        self._app = app
        self.title("Ask Gemini")
        self.geometry("540x420")
        self.minsize(400, 300)
        self.wm_attributes("-topmost", True)
        self._build()
        self.lift()
        self.after(80, self._question_entry.focus_set)

    def _build(self) -> None:
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        # ── Question row ──
        q_row = ctk.CTkFrame(self, fg_color="transparent")
        q_row.grid(row=0, column=0, sticky="ew", padx=12, pady=(12, 6))
        q_row.columnconfigure(0, weight=1)

        self._question_var = ctk.StringVar()
        self._question_entry = ctk.CTkEntry(
            q_row, textvariable=self._question_var,
            placeholder_text="Ask Gemini anything…",
            height=34, font=ctk.CTkFont(size=13),
        )
        self._question_entry.grid(row=0, column=0, sticky="ew", padx=(0, 8))
        self._question_entry.bind("<Return>", lambda _: self._ask())

        self._ask_btn = ctk.CTkButton(
            q_row, text="Ask", width=72, height=34,
            command=self._ask,
        )
        self._ask_btn.grid(row=0, column=1)

        # ── Result area ──
        import tkinter as tk
        self._result = tk.Text(
            self, wrap="word",
            bg="#0d0d1e", fg="#d8d8f8",
            insertbackground="#7799cc",
            selectbackground="#1e3a6e",
            font=("Consolas", 11),
            relief="flat", borderwidth=0,
            padx=10, pady=8,
            state="disabled",
        )
        self._result.grid(row=1, column=0, sticky="nsew", padx=12, pady=(0, 6))

        # ── Bottom bar ──
        bar = ctk.CTkFrame(self, fg_color="transparent")
        bar.grid(row=2, column=0, sticky="ew", padx=12, pady=(0, 10))

        self._status = ctk.CTkLabel(
            bar, text="", font=ctk.CTkFont(size=11),
            text_color=("#666688", "#666688"), anchor="w",
        )
        self._status.pack(side="left")

        ctk.CTkButton(
            bar, text="Copy result", width=100, height=28,
            fg_color=("#1e2a3a", "#1e2a3a"),
            command=self._copy_result,
        ).pack(side="right", padx=(4, 0))

        ctk.CTkButton(
            bar, text="Clear", width=70, height=28,
            fg_color=("#252535", "#252535"),
            command=self._clear,
        ).pack(side="right")

    def _ask(self) -> None:
        question = self._question_var.get().strip()
        if not question:
            return
        key = self._app.config.settings.gemini_api_key
        if not key:
            self._set_result("[No API key] Add your free Gemini API key in Settings → Gemini.")
            return
        self._ask_btn.configure(state="disabled", text="…")
        self._status.configure(text="Asking Gemini…")
        self._set_result("")
        threading.Thread(target=self._run, args=(key, question), daemon=True).start()

    def _run(self, key: str, question: str) -> None:
        try:
            from core.gemini import call_gemini
            result = call_gemini(key, question)
            self.after(0, lambda: self._set_result(result))
            self.after(0, lambda: self._status.configure(text="Done."))
        except Exception as exc:
            self.after(0, lambda: self._set_result(f"[Error] {exc}"))
            self.after(0, lambda: self._status.configure(text="Error."))
        finally:
            self.after(0, lambda: self._ask_btn.configure(state="normal", text="Ask"))

    def _set_result(self, text: str) -> None:
        import tkinter as tk
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
        self._status.configure(text="Copied.")

    def _clear(self) -> None:
        self._question_var.set("")
        self._set_result("")
        self._status.configure(text="")
        self._question_entry.focus_set()
