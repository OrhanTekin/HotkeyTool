"""
Modal dialog for creating or editing a Binding.
"""
from __future__ import annotations

import copy
import threading
import uuid
from typing import TYPE_CHECKING, List

import customtkinter as ctk
from tkinter import messagebox

from core.models import Action, Binding
from ui import theme
from ui.action_editor import ActionEditor
from ui.widgets import GhostButton, PrimaryButton

if TYPE_CHECKING:
    from app import App


class BindingEditor(ctk.CTkToplevel):
    def __init__(self, parent: ctk.CTkBaseClass, app: "App", binding: Binding | None) -> None:
        super().__init__(parent)
        self.app = app
        self._original = binding

        # Work on a deep copy so cancelling is truly non-destructive
        self._working: Binding = (
            Binding.new() if binding is None else copy.deepcopy(binding)
        )
        self._actions: List[Action] = list(self._working.actions)
        self._editors: List[ActionEditor] = []

        self.title("New Binding" if binding is None else "Edit Binding")
        self.geometry("670x560")
        self.minsize(580, 480)
        self.resizable(True, True)

        # Temporarily force topmost so it doesn't spawn behind the main window;
        # relaxed after rendering so it no longer floats above unrelated apps.
        self.attributes("-topmost", True)
        self.configure(fg_color=theme.BG_SURFACE)

        self._build()

        # grab_set must be delayed on Windows or it silently fails
        self.after(120, self.grab_set)
        # Remove hard topmost after the window is fully drawn so it no longer
        # floats above unrelated apps, only above the HotkeyTool window
        self.after(300, lambda: self.attributes("-topmost", False))
        self.lift()
        self.focus_force()

    # ── layout ───────────────────────────────────────────────────────────────

    def _build(self) -> None:
        # ── Name ──
        row = ctk.CTkFrame(self, fg_color="transparent")
        row.pack(fill="x", padx=18, pady=(14, 0))
        ctk.CTkLabel(row, text="Name:", width=100, anchor="w",
                     font=theme.font(13)).pack(side="left")
        self.name_var = ctk.StringVar(value=self._working.name)
        ctk.CTkEntry(row, textvariable=self.name_var, width=360, height=32,
                     fg_color=theme.BG_INPUT, border_color=theme.BORDER,
                     border_width=1, text_color=theme.TEXT_1, font=theme.font(12),
                     placeholder_text="e.g.  Open YouTube + Discord").pack(side="left", padx=4)

        # ── Hotkey ──
        row2 = ctk.CTkFrame(self, fg_color="transparent")
        row2.pack(fill="x", padx=18, pady=(8, 0))
        ctk.CTkLabel(row2, text="Hotkey:", width=100, anchor="w",
                     font=theme.font(13)).pack(side="left")
        self.hotkey_var = ctk.StringVar(value=self._working.hotkey)
        self.hotkey_entry = ctk.CTkEntry(
            row2, textvariable=self.hotkey_var,
            width=190, height=32,
            fg_color=theme.BG_INPUT, border_color=theme.BORDER,
            border_width=1, text_color=theme.TEXT_1, font=theme.mono(12),
            placeholder_text="ctrl+shift+f3",
        )
        self.hotkey_entry.pack(side="left", padx=4)

        self.record_btn = GhostButton(
            row2, text="Record Hotkey", command=self._record_hotkey,
        )
        self.record_btn.pack(side="left", padx=4)

        self.conflict_label = ctk.CTkLabel(
            row2, text="", text_color=theme.DANGER, font=theme.font(11),
        )
        self.conflict_label.pack(side="left", padx=4)

        # ── Actions header ──
        ahdr = ctk.CTkFrame(self, fg_color="transparent")
        ahdr.pack(fill="x", padx=18, pady=(14, 0))
        ctk.CTkLabel(ahdr, text="Actions",
                     font=theme.font(14, "bold"), text_color=theme.TEXT_1).pack(side="left")
        PrimaryButton(ahdr, text="+ Add Action", small=True,
                      command=self._add_action).pack(side="right")

        # ── Actions scroll ──
        self.actions_scroll = ctk.CTkScrollableFrame(
            self, fg_color=theme.BG_BASE,
            scrollbar_button_color=theme.BG_ELEVATED,
            scrollbar_button_hover_color=theme.BORDER_STRONG,
            corner_radius=8, border_color=theme.BORDER_SOFT, border_width=1,
        )
        self.actions_scroll.pack(fill="both", expand=True, padx=18, pady=(6, 0))
        self._rebuild_editors()

        # ── Footer buttons ──
        foot = ctk.CTkFrame(self, fg_color="transparent", height=54)
        foot.pack(fill="x", padx=18, pady=(6, 14))
        foot.pack_propagate(False)

        GhostButton(foot, text="Cancel", command=self.destroy).pack(side="right", padx=(6, 0))
        PrimaryButton(foot, text="Save Binding", command=self._save).pack(side="right")

    # ── action list management ────────────────────────────────────────────────

    def _rebuild_editors(self) -> None:
        for w in self.actions_scroll.winfo_children():
            w.destroy()
        self._editors.clear()

        if not self._actions:
            ctk.CTkLabel(
                self.actions_scroll,
                text="No actions yet.\nClick '+ Add Action' to add one.",
                font=theme.font(13), text_color=theme.TEXT_3, justify="center",
            ).pack(pady=24)
            return

        for i, action in enumerate(self._actions):
            ed = ActionEditor(
                self.actions_scroll, action=action, index=i,
                on_remove=self._remove_action,
                on_move_up=self._move_up,
                on_move_down=self._move_down,
            )
            ed.pack(fill="x", pady=(0, 5), padx=4)
            self._editors.append(ed)

    def _collect(self) -> List[Action]:
        return [ed.get_action() for ed in self._editors]

    def _add_action(self) -> None:
        self._actions = self._collect()
        self._actions.append(Action(type="open_url", value=""))
        self._rebuild_editors()

    def _remove_action(self, idx: int) -> None:
        self._actions = self._collect()
        if 0 <= idx < len(self._actions):
            self._actions.pop(idx)
        self._rebuild_editors()

    def _move_up(self, idx: int) -> None:
        self._actions = self._collect()
        if idx > 0:
            self._actions[idx - 1], self._actions[idx] = (
                self._actions[idx], self._actions[idx - 1]
            )
        self._rebuild_editors()

    def _move_down(self, idx: int) -> None:
        self._actions = self._collect()
        if idx < len(self._actions) - 1:
            self._actions[idx + 1], self._actions[idx] = (
                self._actions[idx], self._actions[idx + 1]
            )
        self._rebuild_editors()

    # ── hotkey recording ──────────────────────────────────────────────────────

    def _record_hotkey(self) -> None:
        self.record_btn.configure(text="Press any key...", state="disabled")
        self.hotkey_var.set("")
        self.conflict_label.configure(text="")
        self.app.listener.stop()

        def _worker() -> None:
            from utils.hotkey_recorder import record_hotkey
            combo = record_hotkey(timeout=8.0)
            self.after(0, lambda: self._finish_record(combo))

        threading.Thread(target=_worker, daemon=True).start()

    def _finish_record(self, combo: str | None) -> None:
        if combo:
            self.hotkey_var.set(combo)
        self.record_btn.configure(text="Record Hotkey", state="normal")
        if self.app.config.listening:
            self.app.listener.start()

    # ── save ─────────────────────────────────────────────────────────────────

    def _save(self) -> None:
        name   = self.name_var.get().strip()
        hotkey = self.hotkey_var.get().strip()
        actions = self._collect()

        if not name:
            messagebox.showwarning("Validation", "Please enter a binding name.", parent=self)
            return
        if not hotkey:
            messagebox.showwarning("Validation",
                                   "Please record or type a hotkey.", parent=self)
            return

        # Conflict check (exclude the binding being edited)
        for b in self.app.config.bindings:
            if b.hotkey.lower() == hotkey.lower():
                if self._original is None or b.id != self._original.id:
                    self.conflict_label.configure(text=f"\u26a0 Conflict: '{b.name}'")
                    messagebox.showwarning(
                        "Hotkey Conflict",
                        f"The hotkey '{hotkey}' is already used by '{b.name}'.\n"
                        "Please choose a different hotkey.",
                        parent=self,
                    )
                    return

        self.conflict_label.configure(text="")
        self._working.name    = name
        self._working.hotkey  = hotkey
        self._working.actions = actions

        if self._original is None:
            self.app.config.bindings.append(self._working)
        else:
            idx = next(
                (i for i, b in enumerate(self.app.config.bindings)
                 if b.id == self._original.id),
                None,
            )
            if idx is not None:
                self.app.config.bindings[idx] = self._working

        self.app.save_and_reload()
        self.destroy()
