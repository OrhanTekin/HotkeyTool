"""
Window Layouts tab: capture and restore named window arrangements.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

import customtkinter as ctk
from tkinter import messagebox

if TYPE_CHECKING:
    from app import App
    from core.models import WindowLayout

_ROW_EVEN = ("#1a1a2e", "#1a1a2e")
_ROW_ODD  = ("#16162a", "#16162a")


class LayoutsTab(ctk.CTkFrame):
    def __init__(self, parent: ctk.CTkBaseClass, app: "App") -> None:
        super().__init__(parent, fg_color="transparent")
        self.app = app
        self._rows: list[_LayoutRow] = []
        self._build()
        self.refresh()

    def _build(self) -> None:
        tb = ctk.CTkFrame(self, fg_color="transparent", height=50)
        tb.pack(fill="x", padx=4, pady=(4, 0))
        tb.pack_propagate(False)

        ctk.CTkButton(
            tb, text="📸  Capture Current Layout",
            width=200, height=36,
            font=ctk.CTkFont(size=13, weight="bold"),
            command=self._capture,
        ).pack(side="left", padx=(0, 8))

        ctk.CTkLabel(
            tb,
            text="Snapshots all open window positions & sizes",
            font=ctk.CTkFont(size=11),
            text_color=("#555577", "#555577"),
        ).pack(side="left", padx=4)

        # Column headers
        hdr = ctk.CTkFrame(self, fg_color=("#0f0f22", "#0f0f22"), height=28, corner_radius=6)
        hdr.pack(fill="x", padx=4, pady=(6, 0))
        hdr.pack_propagate(False)
        for text, width in [("Name", 200), ("Windows", 80), ("Actions", 0)]:
            ctk.CTkLabel(
                hdr, text=text, width=width, anchor="w",
                font=ctk.CTkFont(size=11, weight="bold"),
                text_color=("#666688", "#666688"),
            ).pack(side="left", padx=(8, 4))

        self._scroll = ctk.CTkScrollableFrame(self, fg_color="transparent")
        self._scroll.pack(fill="both", expand=True, padx=4, pady=(4, 4))

        self._empty = ctk.CTkLabel(
            self._scroll,
            text='No layouts saved yet.\nArrange your windows, then click "Capture Current Layout".',
            font=ctk.CTkFont(size=13),
            text_color=("#444466", "#444466"),
            justify="center",
        )

    def refresh(self) -> None:
        for row in self._rows:
            row.destroy()
        self._rows.clear()

        layouts = self.app.config.layouts
        if not layouts:
            self._empty.pack(pady=48)
        else:
            self._empty.pack_forget()
            for i, layout in enumerate(layouts):
                row = _LayoutRow(self._scroll, self.app, layout, i, self)
                row.pack(fill="x", pady=(0, 2))
                self._rows.append(row)

    def _capture(self) -> None:
        dialog = _NameDialog(self, "Save Layout", "Layout name:",
                             f"Layout {len(self.app.config.layouts) + 1}")
        self.wait_window(dialog)
        name = dialog.result
        if not name or not name.strip():
            return
        from core.layout_manager import capture_layout
        layout = capture_layout(name.strip())
        self.app.config.layouts.append(layout)
        self.app.save_config_only()
        self.refresh()
        messagebox.showinfo(
            "Layout Saved",
            f"Saved layout \"{name}\" with {len(layout.windows)} windows.",
            parent=self,
        )


class _LayoutRow(ctk.CTkFrame):
    def __init__(self, parent, app: "App", layout: "WindowLayout", index: int, tab: LayoutsTab):
        bg = _ROW_EVEN if index % 2 == 0 else _ROW_ODD
        super().__init__(parent, fg_color=bg, corner_radius=6, height=44)
        self.pack_propagate(False)
        self.app = app
        self.layout = layout
        self.tab = tab
        self._build()

    def _build(self) -> None:
        # Name
        ctk.CTkLabel(
            self, text=self.layout.name,
            font=ctk.CTkFont(size=13), width=192, anchor="w",
            text_color=("#d8d8ee", "#d8d8ee"),
        ).pack(side="left", padx=(12, 4), pady=7)

        # Window count
        ctk.CTkLabel(
            self, text=f"{len(self.layout.windows)} win",
            font=ctk.CTkFont(size=11), width=60, anchor="center",
            text_color=("#777799", "#777799"),
        ).pack(side="left", padx=4)

        # Buttons
        btn = ctk.CTkFrame(self, fg_color="transparent")
        btn.pack(side="right", padx=6)

        ctk.CTkButton(btn, text="Delete", width=62, height=28,
                      fg_color=("#5c1a1a","#5c1a1a"), hover_color=("#7a2222","#7a2222"),
                      font=ctk.CTkFont(size=11), command=self._delete,
                      ).pack(side="right", padx=(2, 0))

        ctk.CTkButton(btn, text="Restore", width=72, height=28,
                      fg_color=("#163a22","#163a22"), hover_color=("#1e4a2a","#1e4a2a"),
                      font=ctk.CTkFont(size=11), command=self._restore,
                      ).pack(side="right", padx=2)

    def _restore(self) -> None:
        from core.layout_manager import restore_layout
        matched, total = restore_layout(self.layout)
        messagebox.showinfo(
            "Layout Restored",
            f"Restored {matched} of {total} windows.",
            parent=self.tab,
        )

    def _delete(self) -> None:
        try:
            self.app.config.layouts.remove(self.layout)
        except ValueError:
            pass
        self.app.save_config_only()
        self.tab.refresh()


class _NameDialog(ctk.CTkToplevel):
    def __init__(self, parent, title: str, label: str, initial: str = ""):
        super().__init__(parent)
        self.result: str | None = None
        self.title(title)
        self.geometry("340x130")
        self.resizable(False, False)
        self.attributes("-topmost", True)

        ctk.CTkLabel(self, text=label, font=ctk.CTkFont(size=13)).pack(padx=16, pady=(12, 4))
        self._var = ctk.StringVar(value=initial)
        ctk.CTkEntry(self, textvariable=self._var, width=300, height=30).pack(padx=16)

        row = ctk.CTkFrame(self, fg_color="transparent")
        row.pack(pady=10)
        ctk.CTkButton(row, text="Save", width=80, command=self._ok).pack(side="left", padx=4)
        ctk.CTkButton(row, text="Cancel", width=80,
                      fg_color=("#252535","#252535"), hover_color=("#353548","#353548"),
                      command=self.destroy).pack(side="left", padx=4)

        self.after(120, self.grab_set)
        self.lift()

    def _ok(self) -> None:
        self.result = self._var.get()
        self.destroy()
