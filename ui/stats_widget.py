"""
System stats floating widget: always-on-top panel showing live CPU/RAM/disk/network.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

import customtkinter as ctk

from core.stats_monitor import Stats

if TYPE_CHECKING:
    from app import App


class StatsWidget(ctk.CTkToplevel):
    def __init__(self, app: "App") -> None:
        super().__init__()
        self.app = app
        self._visible = False

        self.title("System Stats")
        self.geometry("230x160")
        self.resizable(False, False)
        self.attributes("-topmost", True)
        self.overrideredirect(True)   # no title bar — draggable by content
        self.protocol("WM_DELETE_WINDOW", self.hide)

        self._build()
        self._start_drag()
        self.withdraw()   # hidden by default

    # ── layout ────────────────────────────────────────────────────────────────

    def _build(self) -> None:
        outer = ctk.CTkFrame(
            self, fg_color=("#0d0d1e", "#0d0d1e"),
            corner_radius=10, border_width=1,
            border_color=("#2a2a44", "#2a2a44"),
        )
        outer.pack(fill="both", expand=True, padx=1, pady=1)

        # Title bar row
        hdr = ctk.CTkFrame(outer, fg_color=("#131328", "#131328"), corner_radius=8, height=28)
        hdr.pack(fill="x", padx=4, pady=(4, 0))
        hdr.pack_propagate(False)

        ctk.CTkLabel(
            hdr, text="System Stats",
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color=("#6688bb", "#6688bb"),
        ).pack(side="left", padx=8)

        ctk.CTkButton(
            hdr, text="✕", width=22, height=22,
            fg_color="transparent", hover_color=("#5c1a1a", "#5c1a1a"),
            font=ctk.CTkFont(size=10),
            command=self.hide,
        ).pack(side="right", padx=4)

        # Stats rows
        self._rows: dict[str, ctk.CTkLabel] = {}
        metrics = [
            ("cpu",  "CPU"),
            ("ram",  "RAM"),
            ("disk", "Disk"),
            ("net",  "Net  ↑/↓"),
        ]
        for key, label in metrics:
            row = ctk.CTkFrame(outer, fg_color="transparent", height=26)
            row.pack(fill="x", padx=6, pady=1)
            row.pack_propagate(False)
            ctk.CTkLabel(
                row, text=label, width=60, anchor="w",
                font=ctk.CTkFont(size=11),
                text_color=("#888899", "#888899"),
            ).pack(side="left")
            val_lbl = ctk.CTkLabel(
                row, text="—",
                font=ctk.CTkFont(size=11, weight="bold"),
                text_color=("#d0d0ee", "#d0d0ee"),
                anchor="w",
            )
            val_lbl.pack(side="left", fill="x", expand=True)
            self._rows[key] = val_lbl

    # ── drag support ──────────────────────────────────────────────────────────

    def _start_drag(self) -> None:
        self._drag_x = 0
        self._drag_y = 0
        self.bind("<ButtonPress-1>",   self._on_drag_start)
        self.bind("<B1-Motion>",       self._on_drag_move)

    def _on_drag_start(self, e) -> None:
        self._drag_x = e.x
        self._drag_y = e.y

    def _on_drag_move(self, e) -> None:
        x = self.winfo_x() + e.x - self._drag_x
        y = self.winfo_y() + e.y - self._drag_y
        self.geometry(f"+{x}+{y}")

    # ── public ────────────────────────────────────────────────────────────────

    def show(self) -> None:
        self._visible = True
        self.deiconify()
        self.lift()
        self.attributes("-topmost", True)

    def hide(self) -> None:
        self._visible = False
        self.withdraw()

    def toggle(self) -> None:
        if self._visible:
            self.hide()
        else:
            self.show()

    def is_visible(self) -> bool:
        return self._visible

    def update_stats(self, stats: Stats) -> None:
        """Called from stats monitor thread via root.after()."""
        self._rows["cpu"].configure(
            text=f"{stats.cpu_pct:.1f}%",
            text_color=_color_for_pct(stats.cpu_pct),
        )
        self._rows["ram"].configure(
            text=f"{stats.ram_pct:.1f}%  ({stats.ram_used_gb:.1f}/{stats.ram_total_gb:.1f} GB)",
            text_color=_color_for_pct(stats.ram_pct),
        )
        self._rows["disk"].configure(
            text=f"{stats.disk_pct:.1f}%  ({stats.disk_used_gb:.0f}/{stats.disk_total_gb:.0f} GB)",
            text_color=_color_for_pct(stats.disk_pct),
        )
        self._rows["net"].configure(
            text=f"{_kb_str(stats.net_sent_kb)} / {_kb_str(stats.net_recv_kb)}",
            text_color=("#d0d0ee", "#d0d0ee"),
        )


def _color_for_pct(pct: float) -> tuple:
    if pct >= 90:
        return ("#ff5555", "#ff5555")
    if pct >= 70:
        return ("#ffaa55", "#ffaa55")
    return ("#55dd88", "#55dd88")


def _kb_str(kb: float) -> str:
    if kb >= 1024:
        return f"{kb/1024:.1f} MB/s"
    return f"{kb:.0f} KB/s"
