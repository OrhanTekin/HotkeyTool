"""
Planner tab — monthly / weekly calendar + task list.

Features
────────
• Filter chips (All / Today / Overdue / This week)
• Smart-grouped task list (Overdue · Today · Tomorrow · This week · Later · Inbox)
• Today card with conic-gradient progress ring + mini agenda
• Stat cards (Overdue · This week · Streak)
• Month + Week view (toggle)
• Recurring tasks (daily / weekly / monthly / yearly)
• Drag-and-drop tasks onto calendar cells
• Subtasks / checklist
• Categories with manage dialog
• Keyboard navigation (arrows / N / T / Enter)
• Day-popup for per-day details

The visual language (colors, fonts, spacing) comes from `ui.theme`.
"""
from __future__ import annotations

import calendar
import copy
import locale
import math
import tkinter as tk
import uuid as _uuid
from datetime import date, datetime, timedelta
from typing import TYPE_CHECKING, Dict, List, Optional

import customtkinter as ctk

from core.models import Todo
from core import planner_stats as ps
from ui import theme
from ui.widgets import FilterChip, GhostButton, IconButton, PrimaryButton, Search

if TYPE_CHECKING:
    from app import App


# ── helpers (preserved from original) ──────────────────────────────────────────

_PRI_COLOR = {"low": theme.PRI_LOW, "medium": theme.PRI_MEDIUM, "high": theme.PRI_HIGH}


def _next_color(todos: list) -> str:
    palette = [theme.ACCENT_DEEP, "#3a5a3a", "#5a4a3a", "#4a3a5a",
               "#5a3a3a", "#3a4a4a", "#3a4a3a", "#4a3a3a"]
    return palette[len(todos) % len(palette)]


def _fmt_time(todo: Todo) -> str:
    if todo.time_type == "duration":
        total = todo.duration_mins
        d, rem = divmod(total, 1440)
        h, m   = divmod(rem, 60)
        parts  = [f"{d}d"] if d else []
        if h: parts.append(f"{h}h")
        if m: parts.append(f"{m}m")
        return " ".join(parts) or "0m"
    if todo.time_type == "timespan":
        return f"{todo.start_time}–{todo.end_time}"
    return ""


def _fmt_date_short(date_str: str) -> str:
    try:
        return datetime.strptime(date_str, "%Y-%m-%d").date().strftime("%b %d")
    except Exception:
        return date_str


def _locale_date_order():
    try:
        lc = locale.getlocale()[0] or ""
        if lc.startswith(("de_", "fr_", "nl_", "pl_", "cs_", "sk_",
                           "hu_", "it_", "es_", "pt_", "tr_", "ro_")):
            return "DMY", "."
        if lc.startswith(("en_US", "en_CA", "en_PH")):
            return "MDY", "/"
        if lc.startswith(("zh_", "ja_", "ko_")):
            return "YMD", "-"
    except Exception:
        pass
    return "DMY", "."


def _is_overdue(todo: Todo) -> bool:
    if todo.completed or not todo.date:
        return False
    try:
        return datetime.strptime(todo.date, "%Y-%m-%d").date() < date.today()
    except Exception:
        return False


def _cat_color(categories: list, cat: str) -> str:
    try:
        return theme.CAT_PALETTE[categories.index(cat) % len(theme.CAT_PALETTE)]
    except ValueError:
        return theme.CAT_PALETTE[0]


def _next_recurrence(todo: Todo) -> Optional[str]:
    if not todo.date or todo.recurrence == "none":
        return None
    try:
        cur = datetime.strptime(todo.date, "%Y-%m-%d").date()
    except Exception:
        return None

    if todo.recurrence == "daily":
        nxt = cur + timedelta(days=1)
    elif todo.recurrence == "weekly":
        days = todo.recurrence_days or [cur.weekday()]
        for offset in range(1, 8):
            candidate = cur + timedelta(days=offset)
            if candidate.weekday() in days:
                nxt = candidate
                break
        else:
            nxt = cur + timedelta(weeks=1)
    elif todo.recurrence == "monthly":
        m = cur.month % 12 + 1
        y = cur.year + (1 if cur.month == 12 else 0)
        import calendar as _cal
        last = _cal.monthrange(y, m)[1]
        nxt = date(y, m, min(cur.day, last))
    elif todo.recurrence == "yearly":
        try:
            nxt = date(cur.year + 1, cur.month, cur.day)
        except ValueError:
            nxt = date(cur.year + 1, cur.month, 28)
    else:
        return None
    return nxt.strftime("%Y-%m-%d")


# ── PlannerTab ─────────────────────────────────────────────────────────────────

class PlannerTab(ctk.CTkFrame):
    SIDEBAR_W = 268   # design: planner-grid-v2 grid-template-columns: 304px 1fr

    def __init__(self, parent, app: "App") -> None:
        super().__init__(parent, fg_color=theme.BG_BASE)
        self.app = app
        self._today      = date.today()
        self._view_mode  = "month"
        self._view_year  = self._today.year
        self._view_month = self._today.month
        self._week_start = self._today - timedelta(days=self._today.weekday())
        self._day_cells: Dict[str, List[tk.Frame]] = {}

        # Drag state
        self._drag_id:      Optional[str]  = None
        self._drag_source:  Optional[str]  = None
        self._drag_press_x  = 0
        self._drag_press_y  = 0
        self._drag_active   = False
        self._drag_ghost:   Optional[tk.Toplevel] = None
        self._hovered_date: Optional[str]  = None

        # Day popup toggle
        self._active_popup:      Optional[_DayPopup] = None
        self._active_popup_date: Optional[str]       = None

        # Selection
        self._selected_date: Optional[str] = self._today.strftime("%Y-%m-%d")

        # Filters
        self._search_var   = tk.StringVar()
        self._quick_filter = "all"   # all / today / overdue / week
        self._show_done    = tk.BooleanVar(value=False)

        self._build()
        self.refresh()
        self.after(200, self._init_default_focus)

    # ── public ────────────────────────────────────────────────────────────────

    def refresh(self) -> None:
        self._refresh_all()

    # ── layout ────────────────────────────────────────────────────────────────

    def _build(self) -> None:
        # left = sidebar, right = today + calendar
        self._left = ctk.CTkFrame(
            self, fg_color=theme.BG_SURFACE, corner_radius=0, width=self.SIDEBAR_W,
        )
        self._left.pack(side="left", fill="y")
        self._left.pack_propagate(False)

        # vertical separator
        ctk.CTkFrame(self, width=1, fg_color=theme.BORDER_SOFT, corner_radius=0
                     ).pack(side="left", fill="y")

        self._right = ctk.CTkFrame(self, fg_color=theme.BG_BASE, corner_radius=0)
        self._right.pack(side="left", fill="both", expand=True)

        self._build_task_panel()
        self._build_today_strip()
        self._build_calendar_panel()

        # global drag bindings
        self.winfo_toplevel().bind("<B1-Motion>",       self._on_drag_motion,  add="+")
        self.winfo_toplevel().bind("<ButtonRelease-1>", self._on_drag_release, add="+")
        self.bind("<Map>", lambda e: self.after(80, self._init_default_focus)
                           if e.widget is self else None)

    # ── task sidebar ──────────────────────────────────────────────────────────

    def _build_task_panel(self) -> None:
        # Header: "Tasks" + counts + Add button
        head = ctk.CTkFrame(self._left, fg_color="transparent")
        head.pack(fill="x", padx=14, pady=(14, 8))

        title_col = ctk.CTkFrame(head, fg_color="transparent")
        title_col.pack(side="left", fill="x", expand=True)
        ctk.CTkLabel(
            title_col, text="Tasks", font=theme.font(13, "bold"),
            text_color=theme.TEXT_1, fg_color="transparent", anchor="w",
        ).pack(anchor="w")
        self._tasks_sub = ctk.CTkLabel(
            title_col, text="0 open · 0 done", font=theme.font(11),
            text_color=theme.TEXT_3, fg_color="transparent", anchor="w",
        )
        self._tasks_sub.pack(anchor="w", pady=(2, 0))

        PrimaryButton(head, text="+  Add", small=True,
                      command=lambda: self._add_task("")).pack(side="right")

        # Search
        search_wrap = ctk.CTkFrame(self._left, fg_color="transparent")
        search_wrap.pack(fill="x", padx=12, pady=(0, 8))
        self._search = Search(
            search_wrap, placeholder="Search tasks...",
            on_change=lambda _q: self._refresh_task_panel(),
            width=400, height=30,
        )
        self._search.pack(fill="x")

        # Filter chips
        chips = ctk.CTkFrame(self._left, fg_color="transparent")
        chips.pack(fill="x", padx=4, pady=(0, 10))
        self._chips: Dict[str, FilterChip] = {}
        for key, label in (("all", "All"), ("today", "Today"),
                           ("overdue", "Overdue"), ("week", "This week")):
            chip = FilterChip(
                chips, text=label, on=(key == "all"),
                command=lambda k=key: self._set_quick_filter(k),
            )
            chip.pack(side="left", padx=(0, 1))
            self._chips[key] = chip

        # Underline for the filter row
        ctk.CTkFrame(self._left, height=1, fg_color=theme.BORDER_SOFT, corner_radius=0
                     ).pack(fill="x", padx=12)

        # Show-done toggle (small footer link)
        done_row = ctk.CTkFrame(self._left, fg_color="transparent")
        done_row.pack(fill="x", padx=12, pady=(8, 0))
        self._done_btn = ctk.CTkButton(
            done_row, text="Show completed",
            font=theme.font(11),
            fg_color="transparent", hover_color=theme.BG_HOVER,
            text_color=theme.TEXT_3, anchor="w",
            command=self._toggle_show_done, height=22,
        )
        self._done_btn.pack(side="left")

        # Scrollable list canvas (use tk.Canvas + Frame for finer control)
        canvas_wrap = ctk.CTkFrame(self._left, fg_color="transparent")
        canvas_wrap.pack(fill="both", expand=True, padx=4, pady=(4, 8))

        self._task_canvas = tk.Canvas(canvas_wrap, bg=theme.BG_SURFACE, highlightthickness=0)
        self._task_canvas.pack(side="left", fill="both", expand=True)
        vsb = tk.Scrollbar(canvas_wrap, orient="vertical",
                           command=self._task_canvas.yview,
                           bg=theme.BG_SURFACE, troughcolor=theme.BG_BASE)
        vsb.pack(side="right", fill="y")
        self._task_canvas.configure(yscrollcommand=vsb.set)

        self._task_inner = tk.Frame(self._task_canvas, bg=theme.BG_SURFACE)
        self._task_canvas_win = self._task_canvas.create_window(
            (0, 0), window=self._task_inner, anchor="nw")
        self._task_inner.bind("<Configure>", self._on_task_resize)
        self._task_canvas.bind("<Configure>",
                               lambda e: self._task_canvas.itemconfig(
                                   self._task_canvas_win, width=e.width))
        for ev in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
            self._task_canvas.bind(ev, self._on_task_scroll)
            self._task_inner.bind(ev, self._on_task_scroll)

    def _on_task_resize(self, _=None):
        self._task_canvas.configure(scrollregion=self._task_canvas.bbox("all"))

    def _on_task_scroll(self, e):
        if e.num == 4:    self._task_canvas.yview_scroll(-1, "units")
        elif e.num == 5:  self._task_canvas.yview_scroll(1, "units")
        else:             self._task_canvas.yview_scroll(int(-e.delta/120), "units")

    def _bind_scroll(self, w):
        for ev in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
            try:
                w.bind(ev, self._on_task_scroll, add="+")
            except Exception:
                pass

    def _set_quick_filter(self, val: str) -> None:
        self._quick_filter = val
        for k, chip in self._chips.items():
            chip.set_state(k == val, badge=0)
        self._refresh_task_panel()

    def _toggle_show_done(self) -> None:
        self._show_done.set(not self._show_done.get())
        self._done_btn.configure(
            text="Hide completed" if self._show_done.get() else "Show completed"
        )
        self._refresh_task_panel()

    # ── today strip + calendar ────────────────────────────────────────────────

    def _build_today_strip(self) -> None:
        """Two-column area above the calendar: Today card + Stat cards (compact)."""
        wrap = ctk.CTkFrame(self._right, fg_color="transparent", height=66)
        wrap.pack(side="top", fill="x", padx=16, pady=(8, 4))
        wrap.pack_propagate(False)
        wrap.grid_columnconfigure(0, weight=1)
        wrap.grid_columnconfigure(1, weight=0, minsize=220)

        # ── Today card ──
        self._today_card = ctk.CTkFrame(
            wrap, fg_color=theme.BG_ELEVATED, corner_radius=10,
            border_color=theme.BORDER_SOFT, border_width=1,
        )
        self._today_card.grid(row=0, column=0, sticky="nsew", padx=(0, 6))

        head_row = ctk.CTkFrame(self._today_card, fg_color="transparent")
        head_row.pack(fill="both", expand=True, padx=10, pady=(6, 4))

        info_col = ctk.CTkFrame(head_row, fg_color="transparent")
        info_col.pack(side="left", fill="x", expand=True)
        self._today_day_lbl = ctk.CTkLabel(
            info_col, text="", font=theme.font(11, "bold"),
            text_color=theme.TEXT_1, fg_color="transparent", anchor="w",
        )
        self._today_day_lbl.pack(anchor="w")
        self._today_sub_lbl = ctk.CTkLabel(
            info_col, text="", font=theme.mono(9),
            text_color=theme.TEXT_3, fg_color="transparent", anchor="w",
        )
        self._today_sub_lbl.pack(anchor="w", pady=(1, 0))

        # Progress ring (24×24 canvas — compact size)
        self._ring_canvas = tk.Canvas(
            head_row, width=24, height=24,
            bg=theme.BG_ELEVATED, highlightthickness=0, bd=0,
        )
        self._ring_canvas.pack(side="right", pady=4)

        # Agenda frame created but not packed — no space at compact height
        self._agenda_frame = ctk.CTkFrame(self._today_card, fg_color="transparent")

        # ── Stat cards column ──
        stats = ctk.CTkFrame(wrap, fg_color="transparent")
        stats.grid(row=0, column=1, sticky="nsew")
        stats.grid_rowconfigure((0, 1), weight=1)
        stats.grid_columnconfigure(0, weight=1)

        self._stat_overdue = _StatCard(stats, label="Overdue")
        self._stat_overdue.grid(row=0, column=0, sticky="nsew", pady=(0, 4))
        self._stat_week    = _StatCard(stats, label="This week")
        self._stat_week.grid(row=1, column=0, sticky="nsew")

    def _build_calendar_panel(self) -> None:
        # Nav header
        nav = ctk.CTkFrame(self._right, fg_color="transparent", height=40)
        nav.pack(side="top", fill="x", padx=14)
        nav.pack_propagate(False)

        IconButton(nav, "‹", command=self._prev_period, kind="ghost", size=28
                   ).pack(side="left")
        self._period_lbl = ctk.CTkLabel(
            nav, text="", font=theme.font(14, "bold"),
            text_color=theme.TEXT_1, fg_color="transparent", width=170, anchor="w",
        )
        self._period_lbl.pack(side="left", padx=8)
        IconButton(nav, "›", command=self._next_period, kind="ghost", size=28
                   ).pack(side="left")

        # Right side: view toggle + Today
        right = ctk.CTkFrame(nav, fg_color="transparent")
        right.pack(side="right")

        GhostButton(right, text="Today", small=True, command=self._go_today
                    ).pack(side="right", padx=(6, 0))

        toggle = ctk.CTkFrame(
            right, fg_color=theme.BG_ELEVATED, corner_radius=7,
            border_color=theme.BORDER_SOFT, border_width=1,
        )
        toggle.pack(side="right")
        self._view_btn_month = ctk.CTkButton(
            toggle, text="Month", height=22, width=58, corner_radius=5,
            font=theme.font(10), fg_color=theme.BG_ROW,
            hover_color=theme.BG_HOVER, text_color=theme.TEXT_1,
            command=lambda: self._set_view("month"),
        )
        self._view_btn_month.pack(side="left", padx=2, pady=2)
        self._view_btn_week = ctk.CTkButton(
            toggle, text="Week", height=22, width=58, corner_radius=5,
            font=theme.font(10), fg_color="transparent",
            hover_color=theme.BG_HOVER, text_color=theme.TEXT_3,
            command=lambda: self._set_view("week"),
        )
        self._view_btn_week.pack(side="left", padx=2, pady=2)

        # Day-of-week strip
        self._dow_frame = ctk.CTkFrame(self._right, fg_color="transparent")
        self._dow_frame.pack(fill="x", padx=14, pady=(8, 0))

        # Calendar grid
        self._grid_frame = tk.Frame(self._right, bg=theme.BG_BASE, takefocus=True)
        self._grid_frame.pack(fill="both", expand=True, padx=14, pady=(0, 12))
        for c in range(7):
            self._grid_frame.columnconfigure(c, weight=1)

        for ev in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
            self._grid_frame.bind(ev, self._on_cal_scroll, add="+")

        self._grid_frame.bind("<Enter>", lambda e: self._grid_frame.focus_set())
        self._right.bind     ("<Enter>", lambda e: self._grid_frame.focus_set())

        self._grid_frame.bind("<Left>",   lambda e: self._move_selection(-1))
        self._grid_frame.bind("<Right>",  lambda e: self._move_selection(1))
        self._grid_frame.bind("<Up>",     lambda e: self._move_selection(-7))
        self._grid_frame.bind("<Down>",   lambda e: self._move_selection(7))
        self._grid_frame.bind("<Return>", lambda e: self._kb_enter())
        self._grid_frame.bind("<n>",      lambda e: self._add_task(self._selected_date or ""))
        self._grid_frame.bind("<N>",      lambda e: self._add_task(self._selected_date or ""))
        self._grid_frame.bind("<t>",      lambda e: self._go_today())
        self._grid_frame.bind("<T>",      lambda e: self._go_today())
        self._grid_frame.bind("<Button-1>", lambda e: self._grid_frame.focus_set())

    def _set_view(self, mode: str) -> None:
        if self._view_mode == mode:
            return
        self._view_mode = mode
        # Restyle toggle buttons
        if mode == "month":
            self._view_btn_month.configure(fg_color=theme.BG_ROW, text_color=theme.TEXT_1)
            self._view_btn_week.configure(fg_color="transparent", text_color=theme.TEXT_3)
        else:
            self._view_btn_week.configure(fg_color=theme.BG_ROW, text_color=theme.TEXT_1)
            self._view_btn_month.configure(fg_color="transparent", text_color=theme.TEXT_3)
        self._refresh_calendar()

    # ── refresh dispatch ──────────────────────────────────────────────────────

    def _refresh_all(self) -> None:
        self._today = date.today()
        self._refresh_chips()
        self._refresh_task_panel()
        self._refresh_today_strip()
        self._refresh_calendar()

    def _refresh_chips(self) -> None:
        for k, chip in self._chips.items():
            chip.set_state(k == self._quick_filter, badge=0)

    # ── task list with smart grouping ─────────────────────────────────────────

    def _filtered_todos(self) -> List[Todo]:
        todos = [t for t in self.app.config.todos if not t.completed]
        q = self._search.get().strip().lower()
        if q:
            todos = [t for t in todos if q in t.text.lower() or q in t.category.lower()]

        today_str = self._today.strftime("%Y-%m-%d")
        week_end  = (self._today + timedelta(days=7)).strftime("%Y-%m-%d")
        if self._quick_filter == "today":
            todos = [t for t in todos if t.date == today_str]
        elif self._quick_filter == "overdue":
            todos = [t for t in todos if _is_overdue(t)]
        elif self._quick_filter == "week":
            todos = [t for t in todos if t.date and today_str <= t.date <= week_end]
        return todos

    def _group_todos(self, todos: List[Todo]) -> Dict[str, List[Todo]]:
        today_str    = self._today.strftime("%Y-%m-%d")
        tomorrow_str = (self._today + timedelta(days=1)).strftime("%Y-%m-%d")
        week_end_str = (self._today + timedelta(days=7)).strftime("%Y-%m-%d")

        groups: Dict[str, List[Todo]] = {
            "Overdue":    [],
            "Today":      [],
            "Tomorrow":   [],
            "This week":  [],
            "Later":      [],
            "Inbox":      [],
        }
        for t in todos:
            if not t.date:
                groups["Inbox"].append(t)
            elif t.date < today_str:
                groups["Overdue"].append(t)
            elif t.date == today_str:
                groups["Today"].append(t)
            elif t.date == tomorrow_str:
                groups["Tomorrow"].append(t)
            elif t.date < week_end_str:
                groups["This week"].append(t)
            else:
                groups["Later"].append(t)
        return groups

    def _refresh_task_panel(self) -> None:
        for w in self._task_inner.winfo_children():
            w.destroy()

        all_todos = self.app.config.todos
        n_open = sum(1 for t in all_todos if not t.completed)
        n_done = sum(1 for t in all_todos if t.completed)
        self._tasks_sub.configure(text=f"{n_open} open · {n_done} done")
        self._refresh_chips()

        todos = self._filtered_todos()
        groups = self._group_todos(todos)

        if not any(groups.values()):
            done_for_check = [t for t in all_todos if t.completed]
            if not (self._show_done.get() and done_for_check):
                empty = tk.Frame(self._task_inner, bg=theme.BG_SURFACE)
                empty.pack(fill="x", pady=40)
                tk.Label(empty, text="✓", bg=theme.BG_SURFACE, fg=theme.TEXT_3,
                         font=theme.font(28).cget("family") and ("Segoe UI", 28),
                         ).pack()
                tk.Label(empty, text="All clear",
                         bg=theme.BG_SURFACE, fg=theme.TEXT_1,
                         font=("Segoe UI", 12, "bold")).pack(pady=(6, 0))
                tk.Label(empty, text="Nothing matches this filter.",
                         bg=theme.BG_SURFACE, fg=theme.TEXT_3,
                         font=("Segoe UI", 10)).pack(pady=(2, 0))
                self._task_inner.update_idletasks()
                self._task_canvas.configure(scrollregion=self._task_canvas.bbox("all"))
                return

        for group_name, group_list in groups.items():
            if not group_list:
                continue

            head = tk.Frame(self._task_inner, bg=theme.BG_SURFACE)
            head.pack(fill="x", pady=(8, 2), padx=4)
            tk.Label(
                head, text=group_name.upper(),
                bg=theme.BG_SURFACE, fg=theme.TEXT_3,
                font=("Segoe UI", 9, "bold"),
            ).pack(side="left", padx=(8, 6))
            tk.Label(
                head, text=str(len(group_list)),
                bg=theme.BG_ELEVATED, fg=theme.TEXT_3,
                font=("Consolas", 9), padx=6,
            ).pack(side="left")
            self._bind_scroll(head)

            # Sort: overdue tasks by date asc, others by priority high→low
            pri_order = {"high": 0, "medium": 1, "low": 2}
            sorted_list = sorted(group_list, key=lambda t: (
                t.date or "z", pri_order.get(t.priority, 1)))

            for todo in sorted_list:
                row = self._make_task_row(todo, overdue=(group_name == "Overdue"))
                self._bind_scroll(row)
                for c in row.winfo_children():
                    self._bind_scroll(c)
                    for gc in c.winfo_children():
                        self._bind_scroll(gc)

        # Completed section
        if self._show_done.get():
            done = [t for t in all_todos if t.completed]
            if done:
                head = tk.Frame(self._task_inner, bg=theme.BG_SURFACE)
                head.pack(fill="x", pady=(12, 2), padx=4)
                tk.Label(head, text="COMPLETED", bg=theme.BG_SURFACE,
                         fg=theme.TEXT_3, font=("Segoe UI", 9, "bold")
                         ).pack(side="left", padx=(8, 6))
                tk.Label(head, text=str(len(done)), bg=theme.BG_ELEVATED,
                         fg=theme.TEXT_3, font=("Consolas", 9), padx=6
                         ).pack(side="left")
                self._bind_scroll(head)
                for todo in reversed(done[-30:]):
                    row = self._make_completed_row(todo)
                    self._bind_scroll(row)
                    for c in row.winfo_children():
                        self._bind_scroll(c)

        self._task_inner.update_idletasks()
        self._task_canvas.configure(scrollregion=self._task_canvas.bbox("all"))

    def _make_task_row(self, todo: Todo, *, overdue: bool) -> tk.Frame:
        bg_color = "#2a1416" if overdue else theme.BG_SURFACE
        row = tk.Frame(self._task_inner, bg=bg_color,
                       highlightthickness=1, highlightbackground=theme.BORDER_SOFT)
        row.pack(fill="x", pady=1, padx=4)

        hover_bg = "#3a1a1d" if overdue else theme.BG_HOVER
        _hovered_row = [False]
        _row_bg_widgets: list = []

        def _on_row_enter(_e=None):
            if _hovered_row[0]:
                return
            _hovered_row[0] = True
            row.configure(highlightbackground=theme.BORDER)
            for w in _row_bg_widgets:
                try: w.configure(bg=hover_bg)
                except Exception: pass

        def _on_row_leave(_e=None):
            if not _hovered_row[0]:
                return
            row.after(15, _check_row_hover)

        def _check_row_hover():
            if not _hovered_row[0]:
                return
            try:
                px, py = row.winfo_pointerxy()
                rx, ry = row.winfo_rootx(), row.winfo_rooty()
                if rx <= px <= rx + row.winfo_width() and ry <= py <= ry + row.winfo_height():
                    return
            except Exception:
                pass
            _hovered_row[0] = False
            row.configure(highlightbackground=theme.BORDER_SOFT)
            for w in _row_bg_widgets:
                try: w.configure(bg=bg_color)
                except Exception: pass

        inner = tk.Frame(row, bg=bg_color)
        inner.pack(fill="x", padx=8, pady=6)

        # Checkbox (canvas-drawn for nice rounded look)
        chk = tk.Canvas(inner, width=16, height=16, bg=bg_color,
                        highlightthickness=0, bd=0, cursor="hand2")
        chk.pack(side="left", padx=(0, 8))
        if todo.completed:
            chk.create_oval(0, 0, 16, 16, fill=theme.SUCCESS, outline="")
            chk.create_text(8, 8, text="✓", fill=theme.BG_BASE,
                            font=("Segoe UI", 9, "bold"))
        else:
            chk.create_rectangle(1, 1, 15, 15, outline=theme.TEXT_4, width=1.5)
        chk.bind("<Button-1>", lambda e, t=todo: self._toggle_complete(t))

        # Priority bar (3px wide)
        pri_col = _PRI_COLOR.get(todo.priority, theme.PRI_MEDIUM)
        bar = tk.Frame(inner, bg=pri_col, width=3, height=28)
        bar.pack(side="left", padx=(0, 8))
        bar.pack_propagate(False)

        # Text + meta column
        col = tk.Frame(inner, bg=bg_color)
        col.pack(side="left", fill="x", expand=True)

        text = todo.text if len(todo.text) <= 40 else todo.text[:38] + "…"
        text_fg = theme.TEXT_3 if overdue else theme.TEXT_1
        tk.Label(col, text=text, bg=bg_color, fg=text_fg,
                 font=("Segoe UI", 11), anchor="w").pack(anchor="w")

        # Meta line
        meta = tk.Frame(col, bg=bg_color)
        meta.pack(anchor="w", pady=(2, 0))
        meta_added = False
        if todo.start_time:
            tk.Label(meta, text=f"⏱ {todo.start_time}",
                     bg=bg_color, fg=theme.TEXT_3,
                     font=("Consolas", 9)).pack(side="left", padx=(0, 6))
            meta_added = True
        ts = _fmt_time(todo)
        if ts and todo.time_type == "duration":
            tk.Label(meta, text=ts, bg=bg_color, fg=theme.TEXT_3,
                     font=("Segoe UI", 9)).pack(side="left", padx=(0, 6))
            meta_added = True
        if todo.recurrence != "none":
            tk.Label(meta, text="↻", bg=bg_color, fg=theme.ACCENT,
                     font=("Segoe UI", 10)).pack(side="left", padx=(0, 4))
            meta_added = True
        if todo.subtasks:
            done = sum(1 for s in todo.subtasks if s.get("completed"))
            tk.Label(meta, text=f"☑{done}/{len(todo.subtasks)}",
                     bg=bg_color, fg=theme.TEXT_3,
                     font=("Segoe UI", 9)).pack(side="left", padx=(0, 6))
            meta_added = True
        if todo.category:
            cat_col = _cat_color(self.app.config.planner_categories, todo.category)
            tk.Label(meta, text="●", bg=bg_color, fg=cat_col,
                     font=("Segoe UI", 8)).pack(side="left", padx=(2, 2))
            tk.Label(meta, text=todo.category, bg=bg_color, fg=theme.TEXT_3,
                     font=("Segoe UI", 9)).pack(side="left")
            meta_added = True
        if todo.date and not (todo.start_time):
            tk.Label(meta, text=_fmt_date_short(todo.date),
                     bg=bg_color, fg=theme.TEXT_3,
                     font=("Segoe UI", 9)).pack(side="left", padx=(0, 6))
            meta_added = True
        if not meta_added:
            meta.pack_forget()

        # Right-side action buttons (visible always — minimal icons)
        btn_f = tk.Frame(inner, bg=bg_color)
        btn_f.pack(side="right")
        tk.Button(btn_f, text="✏", command=lambda t=todo: self._edit_task(t),
                  bg=bg_color, fg=theme.TEXT_3, activebackground=theme.BG_HOVER,
                  relief="flat", font=("Segoe UI", 10), cursor="hand2", bd=0
                  ).pack(side="left", padx=2)
        tk.Button(btn_f, text="✕", command=lambda t=todo: self._delete_task(t),
                  bg=bg_color, fg=theme.DANGER, activebackground=theme.DANGER_BG,
                  relief="flat", font=("Segoe UI", 10), cursor="hand2", bd=0
                  ).pack(side="left", padx=2)

        # Deferred setup: hover + drag on all descendants (after widget tree is ready)
        def _setup_row(w, _in_btn_f=False):
            # Hover on every widget so hovering anywhere activates the row effect
            try:
                w.bind("<Enter>", _on_row_enter, add="+")
                w.bind("<Leave>", _on_row_leave, add="+")
            except Exception:
                pass
            # Track for bg-change on hover (all except priority bar)
            if w is not bar:
                _row_bg_widgets.append(w)
            # Drag + cursor: skip btn_f subtree and chk
            if not _in_btn_f and w is not btn_f and w is not chk:
                try:
                    w.configure(cursor="fleur")
                except Exception:
                    pass
                try:
                    w.bind("<ButtonPress-1>",
                           lambda e, tid=todo.id, r=row: self._badge_press(tid, None, e, r),
                           add="+")
                except Exception:
                    pass
            for child in w.winfo_children():
                _setup_row(child, _in_btn_f=_in_btn_f or (w is btn_f))
        row.after(0, lambda: _setup_row(row))

        return row

    def _make_completed_row(self, todo: Todo) -> tk.Frame:
        row = tk.Frame(self._task_inner, bg=theme.BG_SURFACE)
        row.pack(fill="x", pady=1, padx=4)
        inner = tk.Frame(row, bg=theme.BG_SURFACE)
        inner.pack(fill="x", padx=8, pady=4)
        tk.Label(inner, text="✓", bg=theme.BG_SURFACE,
                 fg=theme.SUCCESS, font=("Segoe UI", 11)
                 ).pack(side="left", padx=(0, 8))
        text = todo.text[:40] + "…" if len(todo.text) > 40 else todo.text
        tk.Label(inner, text=text, bg=theme.BG_SURFACE,
                 fg=theme.TEXT_3, font=("Segoe UI", 10, "overstrike"),
                 anchor="w").pack(side="left", fill="x", expand=True)
        tk.Button(inner, text="↺", bg=theme.BG_SURFACE, fg=theme.TEXT_3,
                  relief="flat", font=("Segoe UI", 10), cursor="hand2", bd=0,
                  command=lambda t=todo: self._undo_complete(t)
                  ).pack(side="right", padx=2)
        tk.Button(inner, text="✕", bg=theme.BG_SURFACE, fg=theme.DANGER,
                  relief="flat", font=("Segoe UI", 10), cursor="hand2", bd=0,
                  command=lambda t=todo: self._delete_task(t)
                  ).pack(side="right", padx=2)
        return row

    def _undo_complete(self, todo: Todo) -> None:
        todo.completed = False
        self.app.save_config_only()
        self._refresh_all()

    # ── today strip ───────────────────────────────────────────────────────────

    def _refresh_today_strip(self) -> None:
        # Day label
        self._today_day_lbl.configure(
            text=self._today.strftime("%A, %b %d"),
        )
        done, total = ps.today_progress(self.app.config.todos, self._today)
        if total == 0:
            self._today_sub_lbl.configure(text="No tasks scheduled")
        else:
            self._today_sub_lbl.configure(text=f"{done} of {total} done")

        progress = (done / total) if total else 0.0
        self._draw_progress_ring(progress, label=f"{int(round(progress*100))}%" if total else "—")

        # Mini agenda
        for w in self._agenda_frame.winfo_children():
            w.destroy()

        today_str = self._today.strftime("%Y-%m-%d")
        todays = [t for t in self.app.config.todos if t.date == today_str]
        todays.sort(key=lambda t: t.start_time or "99:99")

        if not todays:
            ctk.CTkLabel(
                self._agenda_frame, text="Nothing on the calendar today.",
                font=theme.font(11), text_color=theme.TEXT_4, fg_color="transparent",
            ).pack(anchor="w", pady=(2, 0))
        else:
            for todo in todays[:5]:
                self._make_agenda_row(self._agenda_frame, todo)
            if len(todays) > 5:
                ctk.CTkLabel(
                    self._agenda_frame, text=f"+{len(todays) - 5} more",
                    font=theme.font(10), text_color=theme.TEXT_4, fg_color="transparent",
                ).pack(anchor="w", pady=(2, 0))

        # Stats
        overdue = ps.overdue_count(self.app.config.todos, self._today)
        week    = ps.this_week_count(self.app.config.todos, self._today)
        self._stat_overdue.set_value(
            overdue,
            sub="all caught up" if overdue == 0 else "needs attention",
            value_color=theme.TEXT_2 if overdue == 0 else theme.DANGER,
        )
        self._stat_week.set_value(week, sub="tasks ahead")

    def _make_agenda_row(self, parent, todo: Todo) -> None:
        row = ctk.CTkFrame(parent, fg_color="transparent", height=22)
        row.pack(fill="x", pady=1)

        time_text = todo.start_time or "—"
        ctk.CTkLabel(
            row, text=time_text, width=44, anchor="e",
            font=theme.mono(10), text_color=theme.TEXT_3, fg_color="transparent",
        ).pack(side="left")

        pri_col = _PRI_COLOR.get(todo.priority, theme.PRI_MEDIUM)
        ctk.CTkFrame(row, fg_color=pri_col, width=3, height=14, corner_radius=2
                     ).pack(side="left", padx=8, pady=4)

        text = todo.text if len(todo.text) <= 40 else todo.text[:38] + "…"
        text_fg = theme.TEXT_3 if todo.completed else theme.TEXT_1
        ctk.CTkLabel(
            row, text=text, font=theme.font(11),
            text_color=text_fg, fg_color="transparent", anchor="w",
        ).pack(side="left", fill="x", expand=True)

        if todo.category:
            ctk.CTkLabel(
                row, text=todo.category, font=theme.font(10),
                text_color=theme.TEXT_3, fg_color="transparent",
            ).pack(side="right", padx=(4, 0))

    def _draw_progress_ring(self, progress: float, *, label: str) -> None:
        c = self._ring_canvas
        c.delete("all")
        size = 24
        cx = cy = size / 2
        outer_r = 9

        # background ring
        c.create_oval(cx-outer_r, cy-outer_r, cx+outer_r, cy+outer_r,
                      outline=theme.BG_ROW, width=2)

        # progress arc
        if progress > 0:
            extent = max(2, progress * 360 - 0.01)  # avoid full-circle bug
            c.create_arc(
                cx-outer_r+1, cy-outer_r+1, cx+outer_r-1, cy+outer_r-1,
                start=90, extent=-extent,
                style="arc", outline=theme.ACCENT, width=2,
            )

        # center label
        c.create_text(cx, cy, text=label,
                      fill=theme.TEXT_1, font=("Consolas", 7, "bold"))

    # ── calendar ──────────────────────────────────────────────────────────────

    def _refresh_calendar(self) -> None:
        for w in self._dow_frame.winfo_children():
            w.destroy()
        for w in self._grid_frame.winfo_children():
            w.destroy()
        self._day_cells.clear()

        if self._view_mode == "month":
            self._refresh_month_view()
        else:
            self._refresh_week_view()

    def _refresh_month_view(self) -> None:
        yr, mo = self._view_year, self._view_month
        self._period_lbl.configure(text=f"{calendar.month_name[mo]} {yr}")

        for i, d in enumerate(("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")):
            fg = theme.TEXT_3 if i >= 5 else theme.TEXT_4
            ctk.CTkLabel(
                self._dow_frame, text=d.upper(),
                font=theme.font(9, "bold"),
                text_color=fg, fg_color="transparent",
            ).grid(row=0, column=i, sticky="ew", padx=2, pady=4)
            self._dow_frame.grid_columnconfigure(i, weight=1)

        first_wd, days_in_month = calendar.monthrange(yr, mo)
        first_date = date(yr, mo, 1)
        for r in range(6):
            self._grid_frame.rowconfigure(r, weight=1, minsize=70)

        row = 0
        col = first_wd
        for c in range(first_wd):
            self._make_month_cell(row, c, first_date - timedelta(days=first_wd-c), True)
        for day_n in range(1, days_in_month + 1):
            self._make_month_cell(row, col, date(yr, mo, day_n), False)
            col += 1
            if col == 7:
                col = 0
                row += 1
        extra = 0
        while col < 7 and row < 6:
            self._make_month_cell(
                row, col,
                date(yr, mo, days_in_month) + timedelta(days=extra+1),
                True,
            )
            extra += 1
            col += 1
            if col == 7:
                col = 0
                row += 1

    def _make_month_cell(self, row: int, col: int, d: date, other: bool) -> None:
        is_today = (d == self._today)
        ds = d.strftime("%Y-%m-%d")
        selected = (ds == self._selected_date)
        weekend = col >= 5

        todos_d = [t for t in self.app.config.todos if t.date == ds]
        active = [t for t in todos_d if not t.completed]
        all_done = todos_d and all(t.completed for t in todos_d)

        if is_today:
            bg = theme.ACCENT_BG
        elif weekend and not other:
            bg = "#10131a"
        else:
            bg = theme.BG_BASE

        bdr = "#ffffff" if selected else (theme.ACCENT_BORDER if is_today else theme.BORDER_SOFT)
        bth = 2 if (selected or is_today) else 1

        cell = tk.Frame(self._grid_frame, bg=bg,
                        highlightthickness=bth, highlightbackground=bdr,
                        cursor="hand2")
        cell.grid(row=row, column=col, sticky="nsew", padx=0, pady=0)
        self._day_cells.setdefault(ds, []).append(cell)

        for ev in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
            cell.bind(ev, self._on_cal_scroll, add="+")

        # Header row: day number + count badge / done mark
        head = tk.Frame(cell, bg=bg, height=20)
        head.pack(fill="x", padx=6, pady=(4, 2))
        head.pack_propagate(False)

        if is_today:
            num_lbl = tk.Label(
                head, text=str(d.day),
                bg=theme.ACCENT, fg=theme.ACCENT_TEXT,
                font=("Segoe UI", 8, "bold"),
                width=2, padx=2,
            )
            # Pick a badge bg that contrasts with the today cell's ACCENT_BG.
            badge_bg, badge_fg = theme.BG_ELEVATED, theme.ACCENT
        else:
            num_color = theme.TEXT_4 if other else theme.TEXT_2
            num_lbl = tk.Label(
                head, text=str(d.day), bg=bg, fg=num_color,
                font=("Segoe UI", 9, "normal"),
            )
            badge_bg, badge_fg = theme.ACCENT_BG, theme.ACCENT
        num_lbl.pack(side="left")

        # Done tick OR count badge on the top-right of the head row.
        # Done tick wins when every task is completed.
        if all_done:
            tk.Label(head, text="✓",
                     bg=theme.SUCCESS, fg=theme.BG_BASE,
                     font=("Segoe UI", 8, "bold"), padx=3
                     ).pack(side="right")
        elif active:
            tk.Label(head, text=str(len(active)),
                     bg=badge_bg, fg=badge_fg,
                     font=("Segoe UI", 7, "bold"), padx=3
                     ).pack(side="right")

        # Body: priority pills (max 2). Fixed pill height keeps cells
        # visually consistent regardless of task content.
        body = tk.Frame(cell, bg=bg)
        body.pack(fill="x", padx=4)
        for t in active[:2]:
            pill = tk.Frame(body, bg=bg, height=14)
            pill.pack(fill="x", pady=1)
            pill.pack_propagate(False)
            pri_col = _PRI_COLOR.get(t.priority, theme.PRI_MEDIUM)
            tk.Frame(pill, bg=pri_col, width=2).pack(side="left", fill="y")
            label_txt = (t.start_time + " " if t.start_time else "") + t.text[:14]
            tk.Label(pill, text=label_txt, bg=bg, fg=theme.TEXT_2,
                     font=("Segoe UI", 7), anchor="w"
                     ).pack(side="left", padx=(3, 0), fill="both", expand=True)

        # Bind day-click to every widget inside the cell so no dead zones.
        # After() defers until widgets are fully registered in winfo_children().
        def _bind_cell_click(w):
            try:
                w.bind("<Button-1>", lambda e, _ds=ds: self._day_click(_ds, e), add="+")
            except Exception:
                pass
            for child in w.winfo_children():
                _bind_cell_click(child)
        cell.after(0, lambda: _bind_cell_click(cell))
        cell.bind("<Enter>", lambda e, c=cell: self._cell_enter(c))
        cell.bind("<Leave>", lambda e, c=cell, _ds=ds, it=is_today: self._cell_leave(c, _ds, it))

    def _refresh_week_view(self) -> None:
        ws = self._week_start
        we = ws + timedelta(days=6)
        self._period_lbl.configure(text=f"{ws.strftime('%b %d')} – {we.strftime('%b %d, %Y')}")

        # DOW header with day numbers
        for i in range(7):
            d = ws + timedelta(days=i)
            is_today_col = (d == self._today)
            fg = theme.TEXT_3 if i >= 5 else theme.TEXT_2
            if is_today_col:
                fg = theme.ACCENT
            ctk.CTkLabel(
                self._dow_frame,
                text=f"{d.strftime('%a').upper()}\n{d.day}",
                font=theme.font(10, "bold" if is_today_col else "normal"),
                text_color=fg, fg_color="transparent",
            ).grid(row=0, column=i, sticky="ew", padx=2, pady=2)
            self._dow_frame.grid_columnconfigure(i, weight=1)

        zones = [
            ("Any time", None, None),
            ("Morning",  "00:00", "11:59"),
            ("Afternoon", "12:00", "16:59"),
            ("Evening",  "17:00", "23:59"),
        ]
        for r, _ in enumerate(zones):
            self._grid_frame.rowconfigure(r, weight=1, minsize=80)

        for col in range(7):
            d = ws + timedelta(days=col)
            ds = d.strftime("%Y-%m-%d")
            todos_d = [t for t in self.app.config.todos
                       if t.date == ds and not t.completed]
            self._grid_frame.columnconfigure(col, weight=1)

            for r, (zone_name, t_from, t_to) in enumerate(zones):
                if zone_name == "Any time":
                    zone_todos = [t for t in todos_d
                                  if t.time_type != "timespan" or not t.start_time]
                else:
                    zone_todos = [t for t in todos_d
                                  if t.time_type == "timespan" and t.start_time
                                  and t_from <= t.start_time <= t_to]

                cell = tk.Frame(self._grid_frame, bg=theme.BG_BASE,
                                highlightthickness=1,
                                highlightbackground=theme.BORDER_SOFT,
                                cursor="hand2")
                cell.grid(row=r, column=col, sticky="nsew", padx=0, pady=0)
                self._day_cells.setdefault(ds, []).append(cell)

                for ev in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
                    cell.bind(ev, self._on_cal_scroll, add="+")

                # Reserved top strip — present in EVERY cell so that pills in
                # column 0 (which carries the zone label) start at the same y
                # as pills in columns 1..6.  Without this, packing the zone
                # label only in column 0 made each row's first cell look
                # ~13 px taller than its siblings.
                top = tk.Frame(cell, bg=theme.BG_BASE, height=16)
                top.pack(fill="x", side="top")
                top.pack_propagate(False)
                if col == 0:
                    tk.Label(top, text=zone_name.upper(),
                             bg=theme.BG_BASE, fg=theme.TEXT_4,
                             font=("Segoe UI", 7, "bold")
                             ).pack(anchor="w", side="left", padx=4)

                pill_frames: set = set()
                for t in zone_todos[:2]:
                    pill = tk.Frame(cell, bg=theme.BG_BASE, height=16)
                    pill.pack(fill="x", padx=2, pady=1)
                    pill.pack_propagate(False)
                    pill_frames.add(pill)
                    pri_col = _PRI_COLOR.get(t.priority, theme.PRI_MEDIUM)
                    tk.Frame(pill, bg=pri_col, width=2).pack(side="left", fill="y")
                    txt = t.text[:14] + "…" if len(t.text) > 14 else t.text
                    if t.start_time:
                        txt = t.start_time + " " + txt
                    lbl = tk.Label(pill, text=txt, bg=theme.BG_BASE, fg=theme.TEXT_2,
                                   font=("Segoe UI", 7), anchor="w", cursor="fleur")
                    lbl.pack(side="left", padx=(3, 0), fill="both", expand=True)
                    pill.bind("<ButtonPress-1>",
                              lambda e, tid=t.id, _ds=ds: self._badge_press(tid, _ds, e))
                    lbl.bind("<ButtonPress-1>",
                             lambda e, tid=t.id, _ds=ds: self._badge_press(tid, _ds, e))
                if len(zone_todos) > 2:
                    tk.Label(cell, text=f"+{len(zone_todos) - 2}",
                             bg=theme.BG_BASE, fg=theme.TEXT_4,
                             font=("Segoe UI", 7), anchor="w"
                             ).pack(fill="x", padx=6)

                # Bind day-click to all cell descendants except pill subtrees
                def _make_week_cell_binder(the_cell, the_ds, skip_trees):
                    def _bind(w):
                        if w in skip_trees:
                            return
                        try:
                            w.bind("<Button-1>",
                                   lambda e, _ds=the_ds: self._day_click(_ds, e),
                                   add="+")
                        except Exception:
                            pass
                        for child in w.winfo_children():
                            _bind(child)
                    the_cell.after(0, lambda: _bind(the_cell))
                _make_week_cell_binder(cell, ds, pill_frames)
                cell.bind("<Enter>",    lambda e, c=cell: self._cell_enter(c))
                cell.bind("<Leave>",    lambda e, c=cell, _ds=ds: self._cell_leave(c, _ds, False))

    # ── drag & drop ───────────────────────────────────────────────────────────

    def _badge_press(self, todo_id: str, source_date: Optional[str], event,
                     source_row=None) -> None:
        self._drag_id         = todo_id
        self._drag_source     = source_date
        self._drag_press_x    = event.x_root
        self._drag_press_y    = event.y_root
        self._drag_active     = False
        self._drag_ghost      = None
        self._drag_source_row = source_row
        self._drag_source_bg  = None

    def _day_click(self, date_str: str, event) -> None:
        if self._drag_active:
            return
        self._grid_frame.focus_set()
        self._select_date(date_str)
        self._open_day(date_str)

    def _on_drag_motion(self, event) -> None:
        if not self._drag_id:
            return
        if not self._drag_active:
            dx = event.x_root - self._drag_press_x
            dy = event.y_root - self._drag_press_y
            if dx*dx + dy*dy < 64:
                return
            self._drag_active = True
            self._create_drag_ghost(event)
            # Subtly mark the source row as being dragged
            if getattr(self, '_drag_source_row', None):
                try:
                    self._drag_source_bg = self._drag_source_row.cget("bg")
                    self._drag_source_row.configure(
                        highlightbackground=theme.ACCENT, highlightthickness=1)
                except Exception:
                    pass
            # Show all calendar cells as valid drop targets
            for cells in self._day_cells.values():
                for cell in cells:
                    try:
                        cell.configure(highlightbackground=theme.BORDER_STRONG,
                                       highlightthickness=1)
                    except Exception:
                        pass

        if self._drag_ghost:
            self._drag_ghost.geometry(f"+{event.x_root+4}+{event.y_root-14}")

        hovered = self._cell_at(event.x_root, event.y_root)
        if hovered != self._hovered_date:
            if self._hovered_date and self._hovered_date in self._day_cells:
                for cell in self._day_cells[self._hovered_date]:
                    try:
                        cell.configure(highlightbackground=theme.BORDER_STRONG,
                                       highlightthickness=1)
                    except Exception:
                        pass
            self._hovered_date = hovered
            if hovered and hovered in self._day_cells:
                for cell in self._day_cells[hovered]:
                    try:
                        cell.configure(highlightbackground=theme.ACCENT,
                                       highlightthickness=2)
                    except Exception:
                        pass

    def _create_drag_ghost(self, event) -> None:
        todo = next((t for t in self.app.config.todos if t.id == self._drag_id), None)
        if not todo:
            return
        ghost = tk.Toplevel(self.winfo_toplevel())
        ghost.overrideredirect(True)
        ghost.wm_attributes("-topmost", True)
        try:
            ghost.wm_attributes("-alpha", 0.92)
        except Exception:
            pass
        outer = tk.Frame(ghost, bg=theme.BORDER_STRONG, padx=2, pady=2)
        outer.pack()
        body = tk.Frame(outer, bg=theme.BG_ELEVATED, padx=14, pady=8)
        body.pack()
        pri_col = _PRI_COLOR.get(todo.priority, theme.PRI_MEDIUM)
        tk.Frame(body, bg=pri_col, height=2).pack(fill="x", pady=(0, 5))
        tk.Label(body, text=todo.text[:36], bg=theme.BG_ELEVATED,
                 fg=theme.TEXT_1, font=("Segoe UI", 11, "bold"),
                 anchor="w").pack(anchor="w")
        info = []
        if todo.category:           info.append(todo.category)
        ts = _fmt_time(todo)
        if ts:                      info.append(ts)
        if todo.date:               info.append(_fmt_date_short(todo.date))
        if info:
            tk.Label(body, text=" · ".join(info), bg=theme.BG_ELEVATED,
                     fg=theme.TEXT_3, font=("Segoe UI", 9)
                     ).pack(anchor="w", pady=(3, 0))
        tk.Label(body, text="⟶  Drop on a calendar day",
                 bg=theme.BG_ELEVATED, fg=theme.TEXT_4, font=("Segoe UI", 8),
                 ).pack(anchor="w", pady=(5, 0))
        ghost.update_idletasks()
        ghost.geometry(f"+{event.x_root+4}+{event.y_root-14}")
        self._drag_ghost = ghost

    def _on_drag_release(self, event) -> None:
        if not self._drag_id:
            return
        if not self._drag_active:
            src = self._drag_source
            self._drag_id     = None
            self._drag_source = None
            if src:
                self._open_day(src)
            return

        if self._drag_ghost:
            self._drag_ghost.destroy()
            self._drag_ghost = None

        target = self._cell_at(event.x_root, event.y_root)
        if target:
            todo = next((t for t in self.app.config.todos if t.id == self._drag_id), None)
            if todo and target != todo.date:
                todo.date = target
                self.app.save_config_only()
                self._refresh_all()
                if self.app.window:
                    self.app.window.toast("Task moved")

        # Restore all cell highlights to normal
        for ds in list(self._day_cells.keys()):
            self._cell_unhighlight(ds)
        # Restore source row border
        if getattr(self, '_drag_source_row', None):
            try:
                self._drag_source_row.configure(highlightthickness=0)
            except Exception:
                pass
            self._drag_source_row = None
            self._drag_source_bg  = None
        self._drag_id      = None
        self._drag_source  = None
        self._drag_active  = False
        self._hovered_date = None

    def _cell_at(self, rx: int, ry: int) -> Optional[str]:
        for ds, cells in self._day_cells.items():
            for cell in cells:
                try:
                    x, y = cell.winfo_rootx(), cell.winfo_rooty()
                    w, h = cell.winfo_width(), cell.winfo_height()
                    if x <= rx < x + w and y <= ry < y + h:
                        return ds
                except Exception:
                    pass
        return None

    def _cell_enter(self, cell: tk.Frame) -> None:
        if self._drag_id:
            cell.configure(highlightbackground=theme.ACCENT, highlightthickness=2)

    def _cell_leave(self, cell: tk.Frame, ds: str, is_today: bool) -> None:
        if self._drag_active:
            cell.configure(highlightbackground=theme.BORDER_STRONG, highlightthickness=1)
            return

    def _cell_unhighlight(self, ds: str) -> None:
        if ds not in self._day_cells:
            return
        selected = (ds == self._selected_date)
        try:
            d = datetime.strptime(ds, "%Y-%m-%d").date()
            is_today = (d == self._today)
        except Exception:
            is_today = False
        bdr = "#ffffff" if selected else (theme.ACCENT_BORDER if is_today else theme.BORDER_SOFT)
        bth = 2 if (selected or is_today) else 1
        for cell in self._day_cells[ds]:
            try:
                cell.configure(highlightbackground=bdr, highlightthickness=bth)
            except Exception:
                pass

    # ── keyboard / nav ────────────────────────────────────────────────────────

    def _select_date(self, ds: str) -> None:
        prev = self._selected_date
        self._selected_date = ds
        if prev and prev in self._day_cells:
            self._cell_unhighlight(prev)
        if ds in self._day_cells:
            for cell in self._day_cells[ds]:
                try:
                    cell.configure(highlightbackground="#ffffff", highlightthickness=2)
                except Exception:
                    pass

    def _move_selection(self, delta: int) -> None:
        if not self._selected_date:
            self._select_date(date.today().strftime("%Y-%m-%d"))
            return
        try:
            cur = datetime.strptime(self._selected_date, "%Y-%m-%d").date()
            nxt = cur + timedelta(days=delta)
        except Exception:
            return
        ds = nxt.strftime("%Y-%m-%d")
        if self._view_mode == "month":
            if nxt.year != self._view_year or nxt.month != self._view_month:
                self._view_year  = nxt.year
                self._view_month = nxt.month
                self._refresh_calendar()
        else:
            week_end = self._week_start + timedelta(days=6)
            if not (self._week_start <= nxt <= week_end):
                self._week_start = nxt - timedelta(days=nxt.weekday())
                self._refresh_calendar()
        self._select_date(ds)

    def _kb_enter(self) -> None:
        if self._selected_date:
            self._open_day(self._selected_date)

    def _on_cal_scroll(self, event) -> None:
        up = event.num == 4 or (hasattr(event, "delta") and event.delta > 0)
        if up:
            self._prev_period()
        else:
            self._next_period()

    def _prev_period(self) -> None:
        if self._view_mode == "month":
            if self._view_month == 1:
                self._view_month, self._view_year = 12, self._view_year - 1
            else:
                self._view_month -= 1
        else:
            self._week_start -= timedelta(weeks=1)
        self._refresh_calendar()

    def _next_period(self) -> None:
        if self._view_mode == "month":
            if self._view_month == 12:
                self._view_month, self._view_year = 1, self._view_year + 1
            else:
                self._view_month += 1
        else:
            self._week_start += timedelta(weeks=1)
        self._refresh_calendar()

    def _go_today(self) -> None:
        self._today = date.today()
        self._view_year  = self._today.year
        self._view_month = self._today.month
        self._week_start = self._today - timedelta(days=self._today.weekday())
        self._refresh_calendar()
        self._select_date(self._today.strftime("%Y-%m-%d"))

    def _init_default_focus(self) -> None:
        try:
            self._grid_frame.focus_set()
            today_str = self._today.strftime("%Y-%m-%d")
            if today_str in self._day_cells:
                self._select_date(today_str)
        except Exception:
            pass

    # ── task CRUD ─────────────────────────────────────────────────────────────

    def _add_task(self, preset_date: str = "") -> None:
        dlg = _TodoDialog(self, preset_date=preset_date)
        self.wait_window(dlg)
        if dlg.result:
            dlg.result.color = _next_color(self.app.config.todos)
            self.app.config.todos.append(dlg.result)
            self.app.save_config_only()
            self._refresh_all()
            if self.app.window:
                self.app.window.toast("Task added")

    def _edit_task(self, todo: Todo) -> None:
        dlg = _TodoDialog(self, existing=todo)
        self.wait_window(dlg)
        if dlg.result:
            for f in ("text", "time_type", "duration_mins", "start_time",
                      "end_time", "date", "priority", "category",
                      "recurrence", "recurrence_days", "subtasks"):
                setattr(todo, f, getattr(dlg.result, f))
            self.app.save_config_only()
            self._refresh_all()

    def _delete_task(self, todo: Todo) -> None:
        self.app.config.todos = [t for t in self.app.config.todos if t.id != todo.id]
        self.app.save_config_only()
        self._refresh_all()
        if self.app.window:
            self.app.window.toast("Task deleted")

    def _toggle_complete(self, todo: Todo) -> None:
        todo.completed = True
        if todo.recurrence != "none" and todo.date:
            nxt = _next_recurrence(todo)
            if nxt:
                new_todo = copy.deepcopy(todo)
                new_todo.id        = str(_uuid.uuid4())
                new_todo.date      = nxt
                new_todo.completed = False
                new_todo.subtasks  = [
                    {**s, "completed": False} for s in todo.subtasks
                ]
                self.app.config.todos.append(new_todo)
        self.app.save_config_only()
        self._refresh_all()

    # ── day popup ─────────────────────────────────────────────────────────────

    def _open_day(self, date_str: str) -> None:
        if self._drag_active:
            return
        if self._active_popup is not None:
            was_alive = False
            try:
                was_alive = self._active_popup.winfo_exists()
            except Exception:
                pass
            try:
                self._active_popup.destroy()
            except Exception:
                pass
            prev = self._active_popup_date
            self._active_popup      = None
            self._active_popup_date = None
            if was_alive and prev == date_str:
                return
        popup = _DayPopup(self, date_str, self.app)
        self._active_popup      = popup
        self._active_popup_date = date_str

    def _on_popup_closed(self) -> None:
        self._active_popup      = None
        self._active_popup_date = None


# ── stat card ──────────────────────────────────────────────────────────────────

class _StatCard(ctk.CTkFrame):
    """Compact horizontal stat card: LABEL on left, value on right."""

    def __init__(self, parent, *, label: str, value_color: str = theme.TEXT_1):
        super().__init__(
            parent, fg_color=theme.BG_ELEVATED, corner_radius=8,
            border_color=theme.BORDER_SOFT, border_width=1,
        )
        self._value_color_default = value_color
        row = ctk.CTkFrame(self, fg_color="transparent")
        row.pack(fill="both", expand=True, padx=8)
        ctk.CTkLabel(
            row, text=label.upper(), font=theme.font(8, "bold"),
            text_color=theme.TEXT_3, fg_color="transparent", anchor="w",
        ).pack(side="left")
        self._value = ctk.CTkLabel(
            row, text="0", font=theme.mono(13, "bold"),
            text_color=value_color, fg_color="transparent", anchor="e",
        )
        self._value.pack(side="right")
        self._sub = ctk.CTkLabel(
            self, text="", font=theme.font(8),
            text_color=theme.TEXT_4, fg_color="transparent", anchor="w",
        )

    def set_value(self, value: int, *, sub: str = "", value_color: str | None = None) -> None:
        self._value.configure(text=str(value),
                              text_color=value_color or self._value_color_default)
        self._sub.configure(text=sub)


# ── Todo dialog (from original, lightly themed) ────────────────────────────────

class _TodoDialog(ctk.CTkToplevel):
    def __init__(self, parent, existing: Optional[Todo] = None,
                 preset_date: str = "") -> None:
        super().__init__(parent, fg_color=theme.BG_SURFACE)
        self.result: Optional[Todo] = None
        self.title("Edit Task" if existing else "New Task")
        self.resizable(True, True)
        self.minsize(480, 400)
        self.wm_attributes("-topmost", True)
        self._existing = existing
        self._parent_tab = parent
        self._build(existing, preset_date)
        self.geometry("480x600")
        self.after(120, self.grab_set)
        from utils.resource_path import apply_window_icon
        self.after(200, lambda: apply_window_icon(self))
        self.lift()

    def _build(self, ex: Optional[Todo], preset_date: str) -> None:
        pad = {"padx": 18, "pady": 4}

        btn_row = ctk.CTkFrame(self, fg_color="transparent")
        btn_row.pack(side="bottom", pady=10)
        from ui.widgets import PrimaryButton, GhostButton
        PrimaryButton(btn_row, text="Save", command=self._save).pack(side="left", padx=8)
        GhostButton(btn_row, text="Cancel", command=self.destroy).pack(side="left", padx=8)

        scroll = ctk.CTkScrollableFrame(
            self, fg_color="transparent",
            scrollbar_button_color=theme.BG_ELEVATED,
            scrollbar_button_hover_color=theme.BORDER_STRONG,
        )
        scroll.pack(fill="both", expand=True)

        # Task text
        self._field_label(scroll, "Task")
        self._text_var = ctk.StringVar(value=ex.text if ex else "")
        te = ctk.CTkEntry(
            scroll, textvariable=self._text_var, width=436, height=32,
            fg_color=theme.BG_INPUT, text_color=theme.TEXT_1,
            border_color=theme.BORDER, border_width=1, font=theme.font(12),
        )
        te.pack(**pad)
        te.focus_set()
        te.bind("<Return>", lambda _: self._save())

        # Priority
        self._field_label(scroll, "Priority")
        self._priority = ctk.StringVar(value=ex.priority if ex else "medium")
        pri_row = ctk.CTkFrame(scroll, fg_color="transparent")
        pri_row.pack(fill="x", **pad)
        for val, label, col in (("low", "Low", theme.PRI_LOW),
                                ("medium", "Medium", theme.PRI_MEDIUM),
                                ("high", "High", theme.PRI_HIGH)):
            ctk.CTkRadioButton(
                pri_row, text=label, variable=self._priority, value=val,
                text_color=col, font=theme.font(11),
                fg_color=col, hover_color=col,
            ).pack(side="left", padx=10)

        # Category
        self._field_label(scroll, "Category")
        cat_row = ctk.CTkFrame(scroll, fg_color="transparent")
        cat_row.pack(fill="x", **pad)
        cats = ["(none)"] + list(self._parent_tab.app.config.planner_categories)
        self._cat_var = ctk.StringVar(value=ex.category if (ex and ex.category) else "(none)")
        self._cat_menu_widget = ctk.CTkOptionMenu(
            cat_row, variable=self._cat_var, values=cats,
            width=160, height=28, font=theme.font(11),
            fg_color=theme.BG_ELEVATED, button_color=theme.BG_ELEVATED,
            button_hover_color=theme.BG_HOVER, text_color=theme.TEXT_1,
        )
        self._cat_menu_widget.pack(side="left", padx=(0, 8))
        from ui.widgets import GhostButton
        GhostButton(cat_row, text="Manage categories…", small=True,
                    command=self._manage_categories).pack(side="left")

        # Time
        self._field_label(scroll, "Time")
        self._time_type = ctk.StringVar(value=ex.time_type if ex else "none")
        radio_row = ctk.CTkFrame(scroll, fg_color="transparent")
        radio_row.pack(fill="x", **pad)
        for val, lbl in (("none", "None"), ("duration", "Duration"), ("timespan", "Time range")):
            ctk.CTkRadioButton(
                radio_row, text=lbl, variable=self._time_type, value=val,
                command=self._update_time_fields,
                font=theme.font(11), text_color=theme.TEXT_2,
                fg_color=theme.ACCENT,
            ).pack(side="left", padx=10)

        ex_total = ex.duration_mins if ex else 0
        ex_d, rem = divmod(ex_total, 1440)
        ex_h, ex_m = divmod(rem, 60)
        self._days_var  = ctk.StringVar(value=str(ex_d) if ex_d else "")
        self._hours_var = ctk.StringVar(value=str(ex_h) if ex_h else "")
        self._mins_var  = ctk.StringVar(value=str(ex_m) if ex_m else "")
        start = ex.start_time if ex else ""
        end   = ex.end_time   if ex else ""
        s_h, s_m = (start.split(":")+[""])[:2] if ":" in start else ("","")
        e_h, e_m = (end.split(":")+[""])[:2]   if ":" in end   else ("","")
        self._start_h = ctk.StringVar(value=s_h)
        self._start_m = ctk.StringVar(value=s_m)
        self._end_h   = ctk.StringVar(value=e_h)
        self._end_m   = ctk.StringVar(value=e_m)

        self._time_frame = ctk.CTkFrame(scroll, fg_color="transparent")
        self._time_frame.pack(fill="x", padx=18, pady=(0, 4))
        self._update_time_fields()

        # Date
        self._field_label(scroll, "Date (optional)")
        date_row = ctk.CTkFrame(scroll, fg_color="transparent")
        date_row.pack(fill="x", **pad)

        order, sep = _locale_date_order()
        ex_date = ex.date if ex else preset_date or ""
        try:
            _d = datetime.strptime(ex_date, "%Y-%m-%d").date() if ex_date else None
        except ValueError:
            _d = None
        self._date_d = ctk.StringVar(value=str(_d.day)   if _d else "")
        self._date_m = ctk.StringVar(value=str(_d.month) if _d else "")
        self._date_y = ctk.StringVar(value=str(_d.year)  if _d else "")

        kw = dict(fg_color=theme.BG_INPUT, text_color=theme.TEXT_1,
                  border_color=theme.BORDER, border_width=1, font=theme.font(11))
        fields = {
            "D": ctk.CTkEntry(date_row, textvariable=self._date_d, width=46, height=28, placeholder_text="DD", **kw),
            "M": ctk.CTkEntry(date_row, textvariable=self._date_m, width=46, height=28, placeholder_text="MM", **kw),
            "Y": ctk.CTkEntry(date_row, textvariable=self._date_y, width=62, height=28, placeholder_text="YYYY", **kw),
        }
        for i, key in enumerate(order):
            fields[key].pack(side="left", padx=2)
            ctk.CTkLabel(date_row, text=sep if i < 2 else "",
                         width=10, text_color=theme.TEXT_3,
                         font=theme.font(13)).pack(side="left")
        from ui.widgets import GhostButton
        GhostButton(date_row, text="📅", small=True, command=self._pick_date
                    ).pack(side="left", padx=(8, 0))

        # Recurrence
        self._field_label(scroll, "Recurrence")
        self._recurrence = ctk.StringVar(value=ex.recurrence if ex else "none")
        rec_row = ctk.CTkFrame(scroll, fg_color="transparent")
        rec_row.pack(fill="x", **pad)
        for val, lbl in (("none", "None"), ("daily", "Daily"), ("weekly", "Weekly"),
                         ("monthly", "Monthly"), ("yearly", "Yearly")):
            ctk.CTkRadioButton(
                rec_row, text=lbl, variable=self._recurrence, value=val,
                command=self._update_rec_fields,
                font=theme.font(11), text_color=theme.TEXT_2,
                fg_color=theme.ACCENT,
            ).pack(side="left", padx=6)
        self._rec_frame = ctk.CTkFrame(scroll, fg_color="transparent")
        self._rec_frame.pack(fill="x", padx=18, pady=(0, 4))
        existing_days = ex.recurrence_days if ex else []
        self._rec_day_vars = {i: tk.BooleanVar(value=i in existing_days) for i in range(7)}
        self._update_rec_fields()

        # Subtasks
        self._field_label(scroll, "Subtasks")
        self._subtask_frame = ctk.CTkFrame(scroll, fg_color="transparent")
        self._subtask_frame.pack(fill="x", padx=18, pady=(0, 4))
        self._subtasks: List[dict] = list(ex.subtasks) if ex else []
        self._rebuild_subtasks()

        sub_add_row = ctk.CTkFrame(scroll, fg_color="transparent")
        sub_add_row.pack(fill="x", padx=18, pady=(0, 8))
        self._new_sub_var = ctk.StringVar()
        sub_e = ctk.CTkEntry(
            sub_add_row, textvariable=self._new_sub_var,
            width=310, height=26,
            fg_color=theme.BG_INPUT, text_color=theme.TEXT_1,
            border_color=theme.BORDER, border_width=1, font=theme.font(11),
            placeholder_text="Add subtask…",
        )
        sub_e.pack(side="left", padx=(0, 6))
        sub_e.bind("<Return>", lambda _: self._add_subtask())
        from ui.widgets import PrimaryButton
        PrimaryButton(sub_add_row, text="+ Add", small=True,
                      command=self._add_subtask).pack(side="left")

    def _field_label(self, parent, text: str) -> None:
        ctk.CTkLabel(
            parent, text=text.upper(),
            font=theme.font(10, "bold"),
            text_color=theme.TEXT_3, fg_color="transparent", anchor="w",
        ).pack(fill="x", padx=18, pady=(10, 2))

    def _update_time_fields(self) -> None:
        for w in self._time_frame.winfo_children():
            w.destroy()
        tt = self._time_type.get()
        kw = dict(fg_color=theme.BG_INPUT, text_color=theme.TEXT_1,
                  border_color=theme.BORDER, border_width=1, font=theme.font(11))
        if tt == "duration":
            row = ctk.CTkFrame(self._time_frame, fg_color="transparent")
            row.pack(anchor="w")
            for var, unit in ((self._days_var, "d"), (self._hours_var, "h"), (self._mins_var, "m")):
                ctk.CTkEntry(row, textvariable=var, width=52, height=28,
                             placeholder_text="0", **kw).pack(side="left", padx=(0, 2))
                ctk.CTkLabel(row, text=unit, width=22,
                             font=theme.font(12, "bold"),
                             text_color=theme.ACCENT_MID).pack(side="left", padx=(0, 10))
        elif tt == "timespan":
            row = ctk.CTkFrame(self._time_frame, fg_color="transparent")
            row.pack(anchor="w")
            ctk.CTkLabel(row, text="From", width=36, font=theme.font(11),
                         text_color=theme.TEXT_3).pack(side="left")
            ctk.CTkEntry(row, textvariable=self._start_h, width=46, height=28,
                         placeholder_text="HH", **kw).pack(side="left")
            ctk.CTkLabel(row, text=":", width=10, font=theme.font(13, "bold"),
                         text_color=theme.ACCENT_MID).pack(side="left")
            ctk.CTkEntry(row, textvariable=self._start_m, width=46, height=28,
                         placeholder_text="MM", **kw).pack(side="left", padx=(0, 14))
            ctk.CTkLabel(row, text="To", width=24, font=theme.font(11),
                         text_color=theme.TEXT_3).pack(side="left")
            ctk.CTkEntry(row, textvariable=self._end_h, width=46, height=28,
                         placeholder_text="HH", **kw).pack(side="left")
            ctk.CTkLabel(row, text=":", width=10, font=theme.font(13, "bold"),
                         text_color=theme.ACCENT_MID).pack(side="left")
            ctk.CTkEntry(row, textvariable=self._end_m, width=46, height=28,
                         placeholder_text="MM", **kw).pack(side="left")

    def _update_rec_fields(self) -> None:
        for w in self._rec_frame.winfo_children():
            w.destroy()
        if self._recurrence.get() == "weekly":
            row = ctk.CTkFrame(self._rec_frame, fg_color="transparent")
            row.pack(anchor="w")
            for i, day in enumerate(("Mo", "Tu", "We", "Th", "Fr", "Sa", "Su")):
                ctk.CTkCheckBox(
                    row, text=day, variable=self._rec_day_vars[i],
                    width=46, height=24,
                    checkbox_width=16, checkbox_height=16,
                    font=theme.font(11), text_color=theme.TEXT_2,
                    fg_color=theme.ACCENT, border_color=theme.BORDER_STRONG,
                ).pack(side="left", padx=2)

    def _pick_date(self) -> None:
        try:
            y = int(self._date_y.get()) if self._date_y.get().strip() else date.today().year
            m = int(self._date_m.get()) if self._date_m.get().strip() else date.today().month
        except ValueError:
            y, m = date.today().year, date.today().month
        self.wm_attributes("-topmost", False)
        popup = _DatePickerPopup(self, y, m, self._set_picked_date)
        self.wait_window(popup)
        self.wm_attributes("-topmost", True)

    def _set_picked_date(self, d: date) -> None:
        self._date_d.set(str(d.day))
        self._date_m.set(str(d.month))
        self._date_y.set(str(d.year))

    def _rebuild_subtasks(self) -> None:
        for w in self._subtask_frame.winfo_children():
            w.destroy()
        for sub in self._subtasks:
            row = ctk.CTkFrame(self._subtask_frame, fg_color="transparent")
            row.pack(fill="x", pady=1)
            var = tk.BooleanVar(value=sub.get("completed", False))
            def _chk_changed(v=var, s=sub):
                s["completed"] = v.get()
            ctk.CTkCheckBox(
                row, text=sub["text"], variable=var, command=_chk_changed,
                checkbox_width=16, checkbox_height=16,
                font=theme.font(11), text_color=theme.TEXT_2,
                fg_color=theme.ACCENT, border_color=theme.BORDER_STRONG,
            ).pack(side="left", fill="x", expand=True)
            from ui.widgets import IconButton
            IconButton(row, "✕", kind="danger", size=24,
                       command=lambda s=sub: self._remove_subtask(s)
                       ).pack(side="right")

    def _add_subtask(self) -> None:
        text = self._new_sub_var.get().strip()
        if not text:
            return
        self._subtasks.append({"id": str(_uuid.uuid4()), "text": text, "completed": False})
        self._new_sub_var.set("")
        self._rebuild_subtasks()

    def _remove_subtask(self, sub: dict) -> None:
        self._subtasks = [s for s in self._subtasks if s["id"] != sub["id"]]
        self._rebuild_subtasks()

    def _manage_categories(self) -> None:
        self.wm_attributes("-topmost", False)
        dlg = _CategoryManagerDialog(self, self._parent_tab.app)
        self.wait_window(dlg)
        self.wm_attributes("-topmost", True)
        cats = ["(none)"] + list(self._parent_tab.app.config.planner_categories)
        self._cat_menu_widget.configure(values=cats)
        if self._cat_var.get() not in cats:
            self._cat_var.set("(none)")

    def _save(self) -> None:
        text = self._text_var.get().strip()
        if not text:
            return
        tt  = self._time_type.get()
        dur = 0
        if tt == "duration":
            try:
                dur = (int(self._days_var.get()  or 0) * 1440 +
                       int(self._hours_var.get() or 0) * 60  +
                       int(self._mins_var.get()  or 0))
            except ValueError:
                dur = 0
        start_str = end_str = ""
        if tt == "timespan":
            try:
                start_str = f"{int(self._start_h.get() or 0):02d}:{int(self._start_m.get() or 0):02d}"
                end_str   = f"{int(self._end_h.get()   or 0):02d}:{int(self._end_m.get()   or 0):02d}"
            except ValueError:
                pass
        date_val = ""
        try:
            dv, mv, yv = self._date_d.get().strip(), self._date_m.get().strip(), self._date_y.get().strip()
            if dv and mv and yv:
                date_val = date(int(yv), int(mv), int(dv)).strftime("%Y-%m-%d")
        except (ValueError, TypeError):
            pass
        cat = self._cat_var.get()
        if cat == "(none)":
            cat = ""
        rec_days = [i for i, v in self._rec_day_vars.items() if v.get()] \
                   if self._recurrence.get() == "weekly" else []

        self.result = Todo(
            id            = self._existing.id    if self._existing else str(_uuid.uuid4()),
            text          = text,
            time_type     = tt,
            duration_mins = dur,
            start_time    = start_str,
            end_time      = end_str,
            date          = date_val,
            color         = self._existing.color if self._existing else theme.ACCENT_DEEP,
            completed     = self._existing.completed if self._existing else False,
            priority      = self._priority.get(),
            category      = cat,
            recurrence    = self._recurrence.get(),
            recurrence_days = rec_days,
            subtasks      = list(self._subtasks),
        )
        self.destroy()


# ── date picker (lightly themed) ───────────────────────────────────────────────

class _DatePickerPopup(ctk.CTkToplevel):
    def __init__(self, parent, year: int, month: int, callback) -> None:
        super().__init__(parent, fg_color=theme.BG_SURFACE)
        self._cb    = callback
        self._year  = year
        self._month = month
        self.title("Pick a date")
        self.resizable(False, False)
        self.wm_attributes("-topmost", True)
        self._body = ctk.CTkFrame(self, fg_color="transparent")
        self._body.pack(padx=8, pady=8)
        self._render()
        self.after(80, self.grab_set)
        self.lift()

    def _render(self) -> None:
        for w in self._body.winfo_children():
            w.destroy()
        from ui.widgets import IconButton
        nav = ctk.CTkFrame(self._body, fg_color="transparent")
        nav.pack(fill="x")
        IconButton(nav, "‹", kind="ghost", size=26, command=self._prev).pack(side="left")
        ctk.CTkLabel(nav, text=f"{calendar.month_name[self._month]} {self._year}",
                     font=theme.font(12, "bold"), text_color=theme.TEXT_1,
                     fg_color="transparent", width=160).pack(side="left", expand=True)
        IconButton(nav, "›", kind="ghost", size=26, command=self._next).pack(side="right")

        hf = ctk.CTkFrame(self._body, fg_color="transparent")
        hf.pack(fill="x", pady=(4, 0))
        for i, d in enumerate(("Mo", "Tu", "We", "Th", "Fr", "Sa", "Su")):
            fg = theme.TEXT_3 if i >= 5 else theme.TEXT_4
            ctk.CTkLabel(
                hf, text=d, width=32, height=22,
                font=theme.font(10), text_color=fg, fg_color="transparent",
            ).grid(row=0, column=i)
            hf.columnconfigure(i, weight=1)

        gf = ctk.CTkFrame(self._body, fg_color="transparent")
        gf.pack(fill="both", expand=True, pady=2)
        for c in range(7):
            gf.columnconfigure(c, weight=1)

        today = date.today()
        first_wd, days = calendar.monthrange(self._year, self._month)
        row, col = 0, first_wd
        for day_n in range(1, days + 1):
            d = date(self._year, self._month, day_n)
            is_today = (d == today)
            ctk.CTkButton(
                gf, text=str(day_n), width=32, height=28,
                fg_color=theme.ACCENT_BG_2 if is_today else theme.BG_ELEVATED,
                hover_color=theme.BG_HOVER,
                text_color=theme.ACCENT if is_today else theme.TEXT_1,
                font=theme.font(10, "bold" if is_today else "normal"),
                border_width=0,
                command=lambda _d=d: self._select(_d),
            ).grid(row=row, column=col, padx=1, pady=1)
            col += 1
            if col == 7:
                col, row = 0, row + 1

    def _prev(self):
        if self._month == 1:
            self._month, self._year = 12, self._year - 1
        else:
            self._month -= 1
        self._render()

    def _next(self):
        if self._month == 12:
            self._month, self._year = 1, self._year + 1
        else:
            self._month += 1
        self._render()

    def _select(self, d: date):
        self._cb(d)
        self.destroy()


# ── category manager (lightly themed) ──────────────────────────────────────────

class _CategoryManagerDialog(ctk.CTkToplevel):
    def __init__(self, parent, app: "App") -> None:
        super().__init__(parent, fg_color=theme.BG_SURFACE)
        self._app = app
        self.title("Manage Categories")
        self.geometry("340x400")
        self.resizable(False, True)
        self.wm_attributes("-topmost", True)
        self._build()
        self.after(100, self.grab_set)
        self.lift()
        self.focus_force()

    def _build(self) -> None:
        ctk.CTkLabel(
            self, text="Categories",
            font=theme.font(14, "bold"), text_color=theme.TEXT_1,
            fg_color="transparent",
        ).pack(pady=(14, 4))

        self._list_frame = ctk.CTkScrollableFrame(self, fg_color="transparent")
        self._list_frame.pack(fill="both", expand=True, padx=12)
        self._render_list()

        add_row = ctk.CTkFrame(self, fg_color="transparent")
        add_row.pack(fill="x", padx=12, pady=8)
        self._new_cat_var = ctk.StringVar()
        e = ctk.CTkEntry(
            add_row, textvariable=self._new_cat_var,
            placeholder_text="New category name…", height=30,
            fg_color=theme.BG_INPUT, text_color=theme.TEXT_1,
            border_color=theme.BORDER, border_width=1, font=theme.font(11),
        )
        e.pack(side="left", fill="x", expand=True, padx=(0, 6))
        e.bind("<Return>", lambda _: self._add())
        from ui.widgets import PrimaryButton, GhostButton
        PrimaryButton(add_row, text="+ Add", small=True, command=self._add
                      ).pack(side="left")
        GhostButton(self, text="Done", command=self.destroy).pack(pady=(0, 12))

    def _render_list(self) -> None:
        for w in self._list_frame.winfo_children():
            w.destroy()
        for i, cat in enumerate(self._app.config.planner_categories):
            row = ctk.CTkFrame(self._list_frame, fg_color="transparent")
            row.pack(fill="x", pady=2)
            dot_col = theme.CAT_PALETTE[i % len(theme.CAT_PALETTE)]
            ctk.CTkLabel(row, text="●", text_color=dot_col,
                         fg_color="transparent",
                         width=20).pack(side="left")
            var = ctk.StringVar(value=cat)
            e = ctk.CTkEntry(
                row, textvariable=var, height=28,
                fg_color=theme.BG_INPUT, text_color=theme.TEXT_1,
                border_color=theme.BORDER, border_width=1, font=theme.font(11),
            )
            e.pack(side="left", fill="x", expand=True, padx=4)
            e.bind("<FocusOut>", lambda ev, v=var, c=cat: self._rename(c, v.get()))
            e.bind("<Return>",   lambda ev, v=var, c=cat: self._rename(c, v.get()))
            from ui.widgets import IconButton
            IconButton(row, "✕", kind="danger", size=26,
                       command=lambda c=cat: self._delete(c)
                       ).pack(side="right")

    def _add(self) -> None:
        name = self._new_cat_var.get().strip()
        if name and name not in self._app.config.planner_categories:
            self._app.config.planner_categories.append(name)
            self._app.save_config_only()
        self._new_cat_var.set("")
        self._render_list()

    def _rename(self, old: str, new: str) -> None:
        new = new.strip()
        if not new or new == old:
            return
        cats = self._app.config.planner_categories
        if new not in cats:
            idx = cats.index(old)
            cats[idx] = new
            for t in self._app.config.todos:
                if t.category == old:
                    t.category = new
            self._app.save_config_only()

    def _delete(self, cat: str) -> None:
        self._app.config.planner_categories = [
            c for c in self._app.config.planner_categories if c != cat]
        for t in self._app.config.todos:
            if t.category == cat:
                t.category = ""
        self._app.save_config_only()
        self._render_list()


# ── day popup (lightly themed) ─────────────────────────────────────────────────

class _DayPopup(ctk.CTkToplevel):
    def __init__(self, planner: PlannerTab, date_str: str, app: "App") -> None:
        super().__init__(planner, fg_color=theme.BG_SURFACE)
        self._planner  = planner
        self._date_str = date_str
        self._app      = app
        try:
            d     = datetime.strptime(date_str, "%Y-%m-%d").date()
            title = d.strftime("%A, %d %B %Y")
            overdue = (d < date.today())
        except Exception:
            title   = date_str
            overdue = False
        self.title(title)
        self.geometry("440x500")
        self.wm_attributes("-topmost", True)
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self._build(title, overdue)
        self.lift()

    def _on_close(self):
        self._planner._on_popup_closed()
        self.destroy()

    def _build(self, title: str, overdue: bool) -> None:
        fg_title = theme.DANGER if overdue else theme.TEXT_1
        ctk.CTkLabel(
            self, text=title,
            font=theme.font(13, "bold"), text_color=fg_title,
            fg_color="transparent",
        ).pack(padx=16, pady=(14, 6))

        scroll = ctk.CTkScrollableFrame(self, fg_color="transparent")
        scroll.pack(fill="both", expand=True, padx=10, pady=4)

        todos = sorted(
            [t for t in self._app.config.todos if t.date == self._date_str],
            key=lambda t: t.start_time or "99:99")

        if not todos:
            ctk.CTkLabel(scroll, text="No tasks for this day.",
                         text_color=theme.TEXT_3, fg_color="transparent",
                         font=theme.font(11)).pack(pady=20)
        else:
            for todo in todos:
                self._make_task_row(scroll, todo)

        btn_row = ctk.CTkFrame(self, fg_color="transparent")
        btn_row.pack(pady=8)
        from ui.widgets import PrimaryButton, GhostButton
        PrimaryButton(btn_row, text="+ Add task for this day", small=True,
                      command=lambda: (self._on_close(),
                                       self._planner._add_task(self._date_str))
                      ).pack(side="left", padx=6)
        GhostButton(btn_row, text="Close", small=True,
                    command=self._on_close).pack(side="left", padx=6)

    def _make_task_row(self, parent, todo: Todo) -> None:
        overdue = _is_overdue(todo)
        row = ctk.CTkFrame(
            parent,
            fg_color=theme.DANGER_BG if overdue else theme.BG_ROW,
            corner_radius=8,
            border_color=theme.BORDER_SOFT, border_width=1,
        )
        row.pack(fill="x", pady=4)

        top = ctk.CTkFrame(row, fg_color="transparent")
        top.pack(fill="x", padx=10, pady=(8, 2))

        pri_col = _PRI_COLOR.get(todo.priority, theme.PRI_MEDIUM)
        ctk.CTkFrame(top, width=4, height=28, fg_color=pri_col,
                     corner_radius=2).pack(side="left", padx=(0, 8), fill="y")

        lbl_text = todo.text
        ts = _fmt_time(todo)
        if ts:
            lbl_text += f"  [{ts}]"
        ctk.CTkLabel(top, text=lbl_text, anchor="w",
                     font=theme.font(12),
                     text_color=theme.DANGER if overdue else theme.TEXT_1,
                     fg_color="transparent",
                     ).pack(side="left", fill="x", expand=True)

        if todo.recurrence != "none":
            ctk.CTkLabel(top, text="↻", text_color=theme.ACCENT,
                         fg_color="transparent",
                         font=theme.font(11)).pack(side="left")

        if todo.subtasks:
            sub_frame = ctk.CTkFrame(row, fg_color="transparent")
            sub_frame.pack(fill="x", padx=22, pady=(0, 4))
            for sub in todo.subtasks:
                sub_row = ctk.CTkFrame(sub_frame, fg_color="transparent")
                sub_row.pack(fill="x", pady=1)
                var = tk.BooleanVar(value=sub.get("completed", False))
                def _sub_toggle(v=var, s=sub, t=todo):
                    s["completed"] = v.get()
                    if t.subtasks and all(sx.get("completed") for sx in t.subtasks):
                        self._planner._toggle_complete(t)
                    else:
                        self._app.save_config_only()
                        self._planner._refresh_all()
                ctk.CTkCheckBox(
                    sub_row, text=sub["text"], variable=var, command=_sub_toggle,
                    checkbox_width=14, checkbox_height=14,
                    font=theme.font(11), text_color=theme.TEXT_2,
                    fg_color=theme.ACCENT, border_color=theme.BORDER_STRONG,
                ).pack(side="left")

        action_row = ctk.CTkFrame(row, fg_color="transparent")
        action_row.pack(fill="x", padx=10, pady=(0, 8))
        from ui.widgets import GhostButton, DangerButton
        GhostButton(action_row, text="Unassign", small=True,
                    command=lambda t=todo: self._unassign(t)
                    ).pack(side="right", padx=(4, 0))
        GhostButton(action_row, text="Edit", small=True,
                    command=lambda t=todo: (self._on_close(),
                                            self._planner._edit_task(t))
                    ).pack(side="right", padx=4)

    def _unassign(self, todo: Todo) -> None:
        todo.date = ""
        self._app.save_config_only()
        self._planner._refresh_all()
        self._on_close()
