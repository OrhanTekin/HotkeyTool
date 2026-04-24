"""
Planner tab  —  monthly / weekly calendar + task list.

Features
────────
• Month view  +  Week view  (toggle)
• Overdue detection with banner
• Recurring tasks  (daily / weekly / monthly / yearly)
• Drag between calendar cells and from task panel
• Task priorities  (Low / Medium / High)  — coloured left accent
• Categories / tags  with manage dialog
• Search + quick-filter bar  (All / Unassigned / Overdue / This week)
• Today summary strip  (always visible above calendar)
• Subtasks / checklist  (progress chip in row, checkboxes in day popup)
• Keyboard navigation  (arrows, N, T, Enter)
"""
from __future__ import annotations

import calendar
import copy
import locale
import tkinter as tk
import uuid as _uuid
from datetime import date, datetime, timedelta
from typing import TYPE_CHECKING, Dict, List, Optional

import customtkinter as ctk

from core.models import Todo

if TYPE_CHECKING:
    from app import App

# ── Palette / constants ────────────────────────────────────────────────────────
_PALETTE = [
    "#1e4a6e", "#1e5a3a", "#5a3a1e", "#4a1e5a",
    "#5a1e2a", "#1e4a4a", "#3a4a1e", "#4a3a1e",
]
_PRI_COLOR  = {"low": "#2a8a2a", "medium": "#7a7a2a", "high": "#aa2a2a"}
_CAT_DOTS   = ["#5588cc", "#cc7733", "#44bb66", "#aa44cc",
               "#44bbbb", "#cc4477", "#88bb33", "#bb7744", "#6688aa"]
_TODAY_BG   = "#1a2a4a"
_TODAY_BDR  = "#4a7acc"
_CELL_BG    = "#111122"
_PANEL_BG   = "#0d0d1e"
_HEADER_BG  = "#0a0a18"


def _next_color(todos: list) -> str:
    return _PALETTE[len(todos) % len(_PALETTE)]


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
        return _CAT_DOTS[categories.index(cat) % len(_CAT_DOTS)]
    except ValueError:
        return _CAT_DOTS[0]


def _next_recurrence(todo: Todo) -> Optional[str]:
    """Return the next occurrence date string, or None if not recurring."""
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
    def __init__(self, parent, app: "App") -> None:
        super().__init__(parent, fg_color="transparent")
        self.app = app
        self._today         = date.today()
        self._view_mode     = "month"          # "month" | "week"
        self._view_year     = self._today.year
        self._view_month    = self._today.month
        # Monday of current week
        self._week_start    = self._today - timedelta(days=self._today.weekday())
        self._day_cells: Dict[str, tk.Frame] = {}
        # Drag state
        self._drag_id:       Optional[str]  = None
        self._drag_source:   Optional[str]  = None   # None=task-panel, str=date
        self._drag_press_x   = 0
        self._drag_press_y   = 0
        self._drag_active    = False
        self._drag_ghost:    Optional[tk.Toplevel] = None
        self._hovered_date:  Optional[str]  = None
        # Day popup toggle
        self._active_popup:      Optional[_DayPopup] = None
        self._active_popup_date: Optional[str]       = None
        # Keyboard selection
        self._selected_date: Optional[str] = self._today.strftime("%Y-%m-%d")
        # Filters
        self._search_var    = tk.StringVar()
        self._quick_filter  = tk.StringVar(value="all")   # all/unassigned/overdue/week
        self._cat_filter    = tk.StringVar(value="")
        self._pri_filter    = tk.StringVar(value="")

        self._build()
        self._refresh_all()
        self.after(200, self._init_default_focus)

    # ── layout ────────────────────────────────────────────────────────────────

    def _build(self) -> None:
        self._left = tk.Frame(self, bg=_PANEL_BG, width=280)
        self._left.pack(side="left", fill="y")
        self._left.pack_propagate(False)

        tk.Frame(self, width=1, bg="#1e1e38").pack(side="left", fill="y")

        self._right = tk.Frame(self, bg=_HEADER_BG)
        self._right.pack(side="left", fill="both", expand=True)

        self._build_task_panel()
        self._build_calendar_panel()

        self.winfo_toplevel().bind("<B1-Motion>",       self._on_drag_motion,  add="+")
        self.winfo_toplevel().bind("<ButtonRelease-1>", self._on_drag_release, add="+")
        # Re-focus grid whenever planner tab becomes visible (tab switch)
        self.bind("<Map>", lambda e: self.after(80, self._init_default_focus)
                           if e.widget is self else None)

    # ── task panel ────────────────────────────────────────────────────────────

    def _build_task_panel(self) -> None:
        # Header
        hdr = tk.Frame(self._left, bg=_HEADER_BG, height=44)
        hdr.pack(fill="x")
        hdr.pack_propagate(False)
        tk.Label(hdr, text="Tasks", bg=_HEADER_BG, fg="#99aacc",
                 font=("Segoe UI", 13, "bold")).pack(side="left", padx=10, pady=10)
        tk.Button(hdr, text="+ Add", command=self._add_task,
                  bg="#163a22", fg="#aaddaa", activebackground="#1e4a2a",
                  relief="flat", font=("Segoe UI", 10), cursor="hand2", padx=8,
                  ).pack(side="right", padx=8, pady=8)
        self._show_done = tk.BooleanVar(value=False)
        tk.Checkbutton(
            hdr, text="Done", variable=self._show_done,
            command=self._refresh_task_panel,
            bg=_HEADER_BG, fg="#558855", selectcolor=_HEADER_BG,
            activebackground=_HEADER_BG, activeforeground="#88bb88",
            relief="flat", font=("Segoe UI", 9), cursor="hand2",
        ).pack(side="right", padx=(0, 2), pady=8)

        # Overdue banner (hidden by default, shown dynamically)
        self._overdue_banner = tk.Label(
            self._left, text="", bg="#3a1010", fg="#ffaaaa",
            font=("Segoe UI", 9, "bold"), anchor="w", padx=8, pady=3,
        )

        # Search bar
        search_row = tk.Frame(self._left, bg=_PANEL_BG)
        search_row.pack(fill="x", padx=6, pady=(4, 0))
        self._search_entry = tk.Entry(
            search_row, textvariable=self._search_var,
            bg="#141428", fg="#d8d8f8", insertbackground="#7799cc",
            relief="flat", font=("Segoe UI", 10),
            highlightthickness=1, highlightbackground="#2a2a4a",
            highlightcolor="#4a4a8a",
        )
        self._search_entry.pack(side="left", fill="x", expand=True, ipady=4)
        self._search_var.trace_add("write", lambda *_: self._refresh_task_panel())
        tk.Button(search_row, text="✕",
                  command=lambda: self._search_var.set(""),
                  bg=_PANEL_BG, fg="#555577", relief="flat",
                  font=("Segoe UI", 10), cursor="hand2",
                  ).pack(side="left")
        tk.Label(search_row, text="🔍", bg=_PANEL_BG, fg="#333355",
                 font=("Segoe UI", 10)).pack(side="right")

        # Quick filters
        qf_row = tk.Frame(self._left, bg=_PANEL_BG)
        qf_row.pack(fill="x", padx=6, pady=(4, 0))
        self._qf_buttons: Dict[str, tk.Button] = {}
        for val, label in (("all", "All"), ("unassigned", "Unassigned"),
                            ("overdue", "Overdue"), ("week", "This week")):
            b = tk.Button(
                qf_row, text=label,
                command=lambda v=val: self._set_quick_filter(v),
                bg="#1e2a3a", fg="#8899bb", relief="flat",
                font=("Segoe UI", 9), cursor="hand2", padx=4, pady=2,
            )
            b.pack(side="left", padx=1)
            self._qf_buttons[val] = b
        self._qf_buttons["all"].config(bg="#2a3a5a", fg="#aabbdd")

        # Category + priority filter row
        cp_row = tk.Frame(self._left, bg=_PANEL_BG)
        cp_row.pack(fill="x", padx=6, pady=(3, 0))
        tk.Label(cp_row, text="Cat:", bg=_PANEL_BG, fg="#555577",
                 font=("Segoe UI", 9)).pack(side="left")
        self._cat_menu = ctk.CTkOptionMenu(
            cp_row, variable=self._cat_filter,
            values=["All"] + list(self.app.config.planner_categories),
            command=lambda _: self._refresh_task_panel(), width=90, height=24,
        )
        self._cat_menu.set("All")
        self._cat_menu.pack(side="left", padx=(2, 6))
        tk.Label(cp_row, text="Pri:", bg=_PANEL_BG, fg="#555577",
                 font=("Segoe UI", 9)).pack(side="left")
        self._pri_menu = ctk.CTkOptionMenu(
            cp_row, variable=self._pri_filter,
            values=["All", "High", "Medium", "Low"],
            command=lambda _: self._refresh_task_panel(), width=80, height=24,
        )
        self._pri_menu.set("All")
        self._pri_menu.pack(side="left", padx=2)

        # Scrollable task canvas
        canvas_frame = tk.Frame(self._left, bg=_PANEL_BG)
        canvas_frame.pack(fill="both", expand=True, pady=(4, 0))
        self._task_canvas = tk.Canvas(canvas_frame, bg=_PANEL_BG, highlightthickness=0)
        self._task_canvas.pack(side="left", fill="both", expand=True)
        vsb = tk.Scrollbar(canvas_frame, orient="vertical",
                           command=self._task_canvas.yview,
                           bg=_PANEL_BG, troughcolor="#0a0a16")
        vsb.pack(side="right", fill="y")
        self._task_canvas.configure(yscrollcommand=vsb.set)
        self._task_inner = tk.Frame(self._task_canvas, bg=_PANEL_BG)
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
        if e.num == 4:          self._task_canvas.yview_scroll(-1, "units")
        elif e.num == 5:        self._task_canvas.yview_scroll(1, "units")
        else:                   self._task_canvas.yview_scroll(int(-e.delta/120), "units")

    def _bind_scroll(self, w):
        for ev in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
            w.bind(ev, self._on_task_scroll, add="+")

    def _set_quick_filter(self, val: str) -> None:
        self._quick_filter.set(val)
        for k, b in self._qf_buttons.items():
            b.config(bg="#2a3a5a" if k == val else "#1e2a3a",
                     fg="#aabbdd" if k == val else "#8899bb")
        self._refresh_task_panel()

    # ── calendar panel ────────────────────────────────────────────────────────

    def _build_calendar_panel(self) -> None:
        # Navigation header
        nav = tk.Frame(self._right, bg=_HEADER_BG, height=44)
        nav.pack(fill="x")
        nav.pack_propagate(False)

        tk.Button(nav, text="◀", command=self._prev_period,
                  bg=_HEADER_BG, fg="#9999bb", activebackground="#1e1e38",
                  relief="flat", font=("Segoe UI", 13), width=2, cursor="hand2",
                  ).pack(side="left", padx=8, pady=6)
        self._period_lbl = tk.Label(nav, text="", bg=_HEADER_BG, fg="#c8c8f0",
                                    font=("Segoe UI", 13, "bold"), width=22, anchor="w")
        self._period_lbl.pack(side="left")
        tk.Button(nav, text="▶", command=self._next_period,
                  bg=_HEADER_BG, fg="#9999bb", activebackground="#1e1e38",
                  relief="flat", font=("Segoe UI", 13), width=2, cursor="hand2",
                  ).pack(side="left", padx=2)

        self._view_toggle_btn = tk.Button(
            nav, text="Week view", command=self._toggle_view,
            bg="#1e2a3a", fg="#8899bb", activebackground="#2a3a4a",
            relief="flat", font=("Segoe UI", 9), cursor="hand2", padx=6,
        )
        self._view_toggle_btn.pack(side="right", padx=(4, 12), pady=8)
        tk.Button(nav, text="Today", command=self._go_today,
                  bg="#1e2a3a", fg="#8899bb", activebackground="#2a3a4a",
                  relief="flat", font=("Segoe UI", 10), cursor="hand2", padx=8,
                  ).pack(side="right", padx=4, pady=8)

        # Today summary strip
        self._today_strip_frame = tk.Frame(self._right, bg="#080816", height=32)
        self._today_strip_frame.pack(fill="x")
        self._today_strip_frame.pack_propagate(False)

        # Day-of-week header (rebuilt in _refresh_calendar)
        self._dow_frame = tk.Frame(self._right, bg=_HEADER_BG)
        self._dow_frame.pack(fill="x")

        # Main grid frame
        self._grid_frame = tk.Frame(self._right, bg="#0a0a18", takefocus=True)
        self._grid_frame.pack(fill="both", expand=True, padx=6, pady=(0, 6))
        for c in range(7):
            self._grid_frame.columnconfigure(c, weight=1)

        # Mousewheel → month/week navigation
        for ev in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
            self._grid_frame.bind(ev, self._on_cal_scroll, add="+")

        # Auto-focus grid on mouse enter so arrow keys work without clicking
        self._grid_frame.bind("<Enter>", lambda e: self._grid_frame.focus_set())
        self._right.bind("<Enter>",      lambda e: self._grid_frame.focus_set())

        # Keyboard navigation
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

    # ── refresh ───────────────────────────────────────────────────────────────

    def _refresh_all(self) -> None:
        self._today = date.today()
        self._refresh_task_panel()
        self._refresh_today_strip()
        self._refresh_calendar()

    def _visible_todos(self) -> List[Todo]:
        todos = [t for t in self.app.config.todos if not t.completed]
        # Search
        q = self._search_var.get().strip().lower()
        if q:
            todos = [t for t in todos if q in t.text.lower() or q in t.category.lower()]
        # Quick filter
        qf = self._quick_filter.get()
        today_str = date.today().strftime("%Y-%m-%d")
        week_end  = (date.today() + timedelta(days=6)).strftime("%Y-%m-%d")
        if qf == "unassigned":
            todos = [t for t in todos if not t.date]
        elif qf == "overdue":
            todos = [t for t in todos if _is_overdue(t)]
        elif qf == "week":
            todos = [t for t in todos if today_str <= t.date <= week_end]
        # Category filter
        cf = self._cat_filter.get()
        if cf and cf != "All":
            todos = [t for t in todos if t.category == cf]
        # Priority filter
        pf = self._pri_filter.get().lower()
        if pf and pf != "all":
            todos = [t for t in todos if t.priority == pf]
        return todos

    def _refresh_task_panel(self) -> None:
        # Update category menu in case categories changed
        cats = ["All"] + list(self.app.config.planner_categories)
        self._cat_menu.configure(values=cats)

        for w in self._task_inner.winfo_children():
            w.destroy()

        # Overdue banner
        all_active  = [t for t in self.app.config.todos if not t.completed]
        overdue_cnt = sum(1 for t in all_active if _is_overdue(t))
        if overdue_cnt:
            self._overdue_banner.config(text=f"  ⚠  {overdue_cnt} task{'s' if overdue_cnt > 1 else ''} overdue")
            self._overdue_banner.pack(fill="x", after=None)
            # Re-pack: banner goes between header and search
            self._overdue_banner.pack_forget()
            self._overdue_banner.pack(fill="x")
            self._overdue_banner.lift()
        else:
            self._overdue_banner.pack_forget()

        todos = self._visible_todos()
        if not todos:
            msg = "No tasks match the filter." if self._search_var.get() or \
                  self._quick_filter.get() != "all" else "No tasks yet. Press + Add."
            lbl = tk.Label(self._task_inner, text=msg,
                           bg=_PANEL_BG, fg="#333355", font=("Segoe UI", 10))
            lbl.pack(pady=20)
            self._bind_scroll(lbl)
        else:
            for todo in todos:
                row = self._make_task_row(todo)
                self._bind_scroll(row)
                for c in row.winfo_children():
                    self._bind_scroll(c)
                    for gc in c.winfo_children():
                        self._bind_scroll(gc)

        # ── Completed section ──
        if self._show_done.get():
            done = [t for t in self.app.config.todos if t.completed]
            if done:
                sep = tk.Label(self._task_inner, text="─── Completed ───",
                               bg=_PANEL_BG, fg="#333355", font=("Segoe UI", 8))
                sep.pack(pady=(8, 2))
                self._bind_scroll(sep)
                for todo in reversed(done[-30:]):
                    row = self._make_completed_row(todo)
                    self._bind_scroll(row)
                    for c in row.winfo_children():
                        self._bind_scroll(c)

        self._task_inner.update_idletasks()
        self._task_canvas.configure(scrollregion=self._task_canvas.bbox("all"))

    def _make_task_row(self, todo: Todo) -> tk.Frame:
        overdue  = _is_overdue(todo)
        assigned = bool(todo.date)
        row_bg   = "#180808" if overdue else ("#10101e" if assigned else "#14142a")
        pri_col  = _PRI_COLOR.get(todo.priority, "#7a7a2a")

        outer = tk.Frame(self._task_inner, bg=pri_col, cursor="fleur")
        outer.pack(fill="x", pady=2, padx=2)

        tk.Frame(outer, width=4, bg=pri_col).pack(side="left", fill="y")

        inner = tk.Frame(outer, bg=row_bg)
        inner.pack(side="left", fill="both", expand=True)

        # Checkbox
        chk_sym = "☑" if todo.completed else "☐"
        chk_fg  = "#55cc55" if todo.completed else "#8899bb"
        tk.Button(inner, text=chk_sym,
                  command=lambda t=todo: self._toggle_complete(t),
                  bg=row_bg, fg=chk_fg, activebackground=row_bg,
                  relief="flat", font=("Segoe UI", 12), cursor="hand2", bd=0, padx=2,
                  ).pack(side="left", padx=(3, 0), pady=2)

        # Recurring badge
        if todo.recurrence != "none":
            tk.Label(inner, text="↻", bg=row_bg, fg="#4a8acc",
                     font=("Segoe UI", 10)).pack(side="left", padx=1)

        # Task text
        display = todo.text if len(todo.text) <= 22 else todo.text[:20] + "…"
        txt_fg  = "#cc6644" if overdue else ("#666677" if assigned else "#c8c8e8")
        lbl = tk.Label(inner, text=display, bg=row_bg, fg=txt_fg,
                       font=("Segoe UI", 10), anchor="w")
        lbl.pack(side="left", padx=3, pady=4)

        # Overdue label
        if overdue:
            tk.Label(inner, text="Overdue", bg="#3a1010", fg="#ff8866",
                     font=("Segoe UI", 7), padx=3).pack(side="left", padx=1)

        # Category dot
        if todo.category:
            cat_col = _cat_color(self.app.config.planner_categories, todo.category)
            tk.Label(inner, text="●", bg=row_bg, fg=cat_col,
                     font=("Segoe UI", 8)).pack(side="left", padx=1)

        # Date badge
        if assigned:
            tk.Label(inner, text=f"📅{_fmt_date_short(todo.date)}",
                     bg=row_bg, fg="#4a6a99", font=("Segoe UI", 7),
                     ).pack(side="left", padx=1)

        # Time badge
        ts = _fmt_time(todo)
        if ts:
            tk.Label(inner, text=ts, bg=row_bg, fg="#7788aa",
                     font=("Segoe UI", 7)).pack(side="left", padx=1)

        # Subtask chip
        if todo.subtasks:
            done_sub = sum(1 for s in todo.subtasks if s.get("completed"))
            total_sub = len(todo.subtasks)
            chip_fg = "#55cc55" if done_sub == total_sub else "#8899bb"
            tk.Label(inner, text=f"☑{done_sub}/{total_sub}",
                     bg=row_bg, fg=chip_fg, font=("Segoe UI", 7),
                     ).pack(side="left", padx=1)

        # Action buttons
        btn_f = tk.Frame(inner, bg=row_bg)
        btn_f.pack(side="right", padx=2)
        tk.Button(btn_f, text="✏", command=lambda t=todo: self._edit_task(t),
                  bg=row_bg, fg="#6688bb", activebackground="#1e2a3a",
                  relief="flat", font=("Segoe UI", 10), cursor="hand2",
                  ).pack(side="left")
        tk.Button(btn_f, text="✕", command=lambda t=todo: self._delete_task(t),
                  bg=row_bg, fg="#885555", activebackground="#3a1616",
                  relief="flat", font=("Segoe UI", 10), cursor="hand2",
                  ).pack(side="left")

        # Drag from task panel
        for w in (outer, lbl, inner):
            w.bind("<ButtonPress-1>",
                   lambda e, tid=todo.id: self._badge_press(tid, None, e))

        return outer

    def _make_completed_row(self, todo: Todo) -> tk.Frame:
        row = tk.Frame(self._task_inner, bg="#0c0c1a")
        row.pack(fill="x", pady=1, padx=2)
        tk.Label(row, text="☑", bg="#0c0c1a", fg="#336633",
                 font=("Segoe UI", 10)).pack(side="left", padx=(4, 1))
        display = todo.text[:24] + "…" if len(todo.text) > 24 else todo.text
        tk.Label(row, text=display, bg="#0c0c1a", fg="#336633",
                 font=("Segoe UI", 9, "overstrike"),
                 anchor="w").pack(side="left", padx=2, fill="x", expand=True)
        tk.Button(row, text="✕", bg="#0c0c1a", fg="#553333",
                  activebackground="#1a0a0a", relief="flat",
                  font=("Segoe UI", 9), cursor="hand2",
                  command=lambda t=todo: self._delete_task(t),
                  ).pack(side="right", padx=2)
        tk.Button(row, text="↺", bg="#0c0c1a", fg="#335577",
                  activebackground="#0a0a1a", relief="flat",
                  font=("Segoe UI", 10), cursor="hand2",
                  command=lambda t=todo: self._undo_complete(t),
                  ).pack(side="right", padx=1)
        return row

    def _undo_complete(self, todo: Todo) -> None:
        todo.completed = False
        self.app.save_config_only()
        self._refresh_all()

    # ── today strip ───────────────────────────────────────────────────────────

    def _refresh_today_strip(self) -> None:
        for w in self._today_strip_frame.winfo_children():
            w.destroy()

        today_str = date.today().strftime("%Y-%m-%d")
        todays = [t for t in self.app.config.todos
                  if t.date == today_str and not t.completed]
        todays.sort(key=lambda t: t.start_time or "99:99")

        tk.Label(self._today_strip_frame, text="Today:",
                 bg="#080816", fg="#556677", font=("Segoe UI", 9, "bold"),
                 ).pack(side="left", padx=(8, 4))

        if not todays:
            tk.Label(self._today_strip_frame, text="No tasks scheduled",
                     bg="#080816", fg="#333355", font=("Segoe UI", 9),
                     ).pack(side="left", padx=4)
            return

        for todo in todays[:7]:
            time_s = todo.start_time or ""
            text   = (f"{time_s} " if time_s else "") + todo.text[:18]
            pill   = tk.Frame(self._today_strip_frame, bg=todo.color,
                              cursor="hand2", padx=6, pady=1)
            pill.pack(side="left", padx=2, pady=4)
            tk.Label(pill, text=text, bg=todo.color, fg="#e8e8ff",
                     font=("Segoe UI", 8)).pack()
            pill.bind("<Button-1>", lambda e, t=todo: self._edit_task(t))

        if len(todays) > 7:
            tk.Label(self._today_strip_frame,
                     text=f"+{len(todays)-7} more",
                     bg="#080816", fg="#445566", font=("Segoe UI", 8),
                     ).pack(side="left", padx=4)

    # ── calendar refresh ──────────────────────────────────────────────────────

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

        self._refresh_today_strip()

    def _refresh_month_view(self) -> None:
        yr, mo = self._view_year, self._view_month
        self._period_lbl.config(text=f"{calendar.month_name[mo]}  {yr}")
        self._view_toggle_btn.config(text="Week view")

        for i, d in enumerate(("Mon","Tue","Wed","Thu","Fri","Sat","Sun")):
            fg = "#6688bb" if i < 5 else "#886688"
            tk.Label(self._dow_frame, text=d, bg=_HEADER_BG, fg=fg,
                     font=("Segoe UI", 10, "bold"),
                     ).grid(row=0, column=i, sticky="ew", padx=2, pady=3)
            self._dow_frame.columnconfigure(i, weight=1)

        first_wd, days_in_month = calendar.monthrange(yr, mo)
        first_date = date(yr, mo, 1)
        row = col = 0
        col = first_wd
        for r in range(6):
            self._grid_frame.rowconfigure(r, weight=1, minsize=76)

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
            self._make_month_cell(row, col,
                date(yr, mo, days_in_month) + timedelta(days=extra+1), True)
            extra += 1
            col += 1
            if col == 7:
                col = 0
                row += 1

    def _make_month_cell(self, row: int, col: int, d: date, other: bool) -> None:
        is_today = (d == self._today)
        ds       = d.strftime("%Y-%m-%d")
        selected = (ds == self._selected_date)
        todos_d  = [t for t in self.app.config.todos
                    if t.date == ds and not t.completed]

        bg  = _TODAY_BG if is_today else ("#0c0c1a" if other else _CELL_BG)
        bdr = ("#eeeeee" if selected else (_TODAY_BDR if is_today else "#1e1e38"))
        bth = 2 if (selected or is_today) else 1

        cell = tk.Frame(self._grid_frame, bg=bg,
                        highlightthickness=bth, highlightbackground=bdr,
                        cursor="hand2")
        cell.grid(row=row, column=col, sticky="nsew", padx=2, pady=2)
        self._day_cells[ds] = cell

        for ev in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
            cell.bind(ev, self._on_cal_scroll, add="+")

        num_fg = _TODAY_BDR if is_today else ("#444455" if other else "#8888aa")
        num_lbl = tk.Label(cell, text=str(d.day), bg=bg, fg=num_fg,
                           font=("Segoe UI", 10, "bold" if is_today else "normal"),
                           anchor="ne")
        num_lbl.pack(fill="x", padx=4, pady=(3, 0))

        # Category dots row
        cats_present = list({t.category for t in todos_d if t.category})
        if cats_present:
            dot_row = tk.Frame(cell, bg=bg)
            dot_row.pack(anchor="ne", padx=4)
            for cat in cats_present[:4]:
                tk.Label(dot_row, text="●",
                         bg=bg, fg=_cat_color(self.app.config.planner_categories, cat),
                         font=("Segoe UI", 7)).pack(side="left")

        # Todo badges (up to 3)
        for todo in todos_d[:3]:
            overdue = _is_overdue(todo)
            badge_bg = "#3a0a0a" if overdue else todo.color
            badge = tk.Frame(cell, bg=badge_bg, height=17)
            badge.pack(fill="x", padx=3, pady=1)
            badge.pack_propagate(False)
            t = todo.text[:20] + "…" if len(todo.text) > 20 else todo.text
            # Subtask chip
            sub_chip = ""
            if todo.subtasks:
                done = sum(1 for s in todo.subtasks if s.get("completed"))
                sub_chip = f" {done}/{len(todo.subtasks)}"
            badge_lbl = tk.Label(badge, text=t + sub_chip,
                                 bg=badge_bg, fg="#ffbbaa" if overdue else "#e8e8ff",
                                 font=("Segoe UI", 8), anchor="w")
            badge_lbl.pack(fill="x", padx=3)
            # Badge drag (with threshold; click → open day)
            badge.bind("<ButtonPress-1>",
                       lambda e, tid=todo.id, _ds=ds: self._badge_press(tid, _ds, e))
            badge_lbl.bind("<ButtonPress-1>",
                           lambda e, tid=todo.id, _ds=ds: self._badge_press(tid, _ds, e))

        if len(todos_d) > 3:
            tk.Label(cell, text=f"+{len(todos_d)-3} more",
                     bg=bg, fg="#555577", font=("Segoe UI", 7),
                     ).pack(anchor="w", padx=4)

        # Click → open day (cell background & number label only)
        cell.bind("<Button-1>",    lambda e, _ds=ds: self._day_click(_ds, e))
        num_lbl.bind("<Button-1>", lambda e, _ds=ds: self._day_click(_ds, e))

        # Hover for drag highlight
        cell.bind("<Enter>", lambda e, c=cell: self._cell_enter(c))
        cell.bind("<Leave>", lambda e, c=cell, _ds=ds, it=is_today: self._cell_leave(c, _ds, it))

    def _refresh_week_view(self) -> None:
        ws  = self._week_start
        we  = ws + timedelta(days=6)
        self._period_lbl.config(
            text=f"{ws.strftime('%b %d')} – {we.strftime('%b %d, %Y')}")
        self._view_toggle_btn.config(text="Month view")

        # DOW header with day numbers
        for i in range(7):
            d   = ws + timedelta(days=i)
            is_today = (d == self._today)
            fg  = "#6688bb" if i < 5 else "#886688"
            day_label = f"{d.strftime('%a')}\n{d.day}"
            bg  = _TODAY_BDR if is_today else fg
            tk.Label(self._dow_frame, text=day_label, bg=_HEADER_BG, fg=bg,
                     font=("Segoe UI", 9, "bold" if is_today else "normal"),
                     ).grid(row=0, column=i, sticky="ew", padx=2, pady=2)
            self._dow_frame.columnconfigure(i, weight=1)

        # 4 time-zone rows
        zones = [("Any time", None, None),
                 ("Morning",  "00:00", "11:59"),
                 ("Afternoon","12:00", "16:59"),
                 ("Evening",  "17:00", "23:59")]

        row_min = [10, 60, 60, 60]
        for r, (zone_name, _, _) in enumerate(zones):
            self._grid_frame.rowconfigure(r, weight=1, minsize=row_min[r])
            tk.Label(self._grid_frame, text=zone_name, bg="#080816", fg="#445566",
                     font=("Segoe UI", 8, "bold"), width=7, anchor="n", pady=4,
                     ).grid(row=r, column=0, sticky="nsew", padx=1, pady=1)

        for col in range(7):
            d  = ws + timedelta(days=col)
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

                cell = tk.Frame(self._grid_frame, bg=_CELL_BG,
                                highlightthickness=1,
                                highlightbackground="#1e1e38",
                                cursor="hand2")
                cell.grid(row=r, column=col, sticky="nsew", padx=1, pady=1)
                self._day_cells[ds] = cell  # last row wins for drop

                for ev in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
                    cell.bind(ev, self._on_cal_scroll, add="+")

                for todo in zone_todos[:2]:
                    overdue  = _is_overdue(todo)
                    badge_bg = "#3a0a0a" if overdue else todo.color
                    badge    = tk.Frame(cell, bg=badge_bg, height=16)
                    badge.pack(fill="x", padx=2, pady=1)
                    badge.pack_propagate(False)
                    txt = todo.text[:16] + "…" if len(todo.text) > 16 else todo.text
                    if todo.start_time:
                        txt = todo.start_time + " " + txt
                    bl = tk.Label(badge, text=txt, bg=badge_bg,
                                  fg="#ffbbaa" if overdue else "#e8e8ff",
                                  font=("Segoe UI", 7), anchor="w")
                    bl.pack(fill="x", padx=2)
                    for w in (badge, bl):
                        w.bind("<ButtonPress-1>",
                               lambda e, tid=todo.id, _ds=ds: self._badge_press(tid, _ds, e))

                if len(zone_todos) > 2:
                    tk.Label(cell, text=f"+{len(zone_todos)-2}",
                             bg=_CELL_BG, fg="#555577", font=("Segoe UI", 7),
                             ).pack(anchor="w")

                cell.bind("<Button-1>", lambda e, _ds=ds: self._day_click(_ds, e))
                cell.bind("<Enter>",    lambda e, c=cell: self._cell_enter(c))
                cell.bind("<Leave>",    lambda e, c=cell, _ds=ds: self._cell_leave(c, _ds, False))

    # ── drag & drop ───────────────────────────────────────────────────────────

    def _badge_press(self, todo_id: str, source_date: Optional[str], event) -> None:
        """Called on <ButtonPress-1> for both task-panel rows and calendar badges."""
        self._drag_id      = todo_id
        self._drag_source  = source_date
        self._drag_press_x = event.x_root
        self._drag_press_y = event.y_root
        self._drag_active  = False
        self._drag_ghost   = None

    def _day_click(self, date_str: str, event) -> None:
        """Handles a click on a calendar cell (not on a badge)."""
        if self._drag_id:
            return   # click suppressed; drag is being handled
        self._grid_frame.focus_set()
        self._select_date(date_str)
        self._open_day(date_str)

    def _on_drag_motion(self, event) -> None:
        if not self._drag_id:
            return
        if not self._drag_active:
            dx = event.x_root - self._drag_press_x
            dy = event.y_root - self._drag_press_y
            if dx*dx + dy*dy < 64:   # threshold 8px
                return
            self._drag_active = True
            self._create_drag_ghost(event)

        if self._drag_ghost:
            self._drag_ghost.geometry(f"+{event.x_root+14}+{event.y_root+10}")

        hovered = self._cell_at(event.x_root, event.y_root)
        if hovered != self._hovered_date:
            if self._hovered_date and self._hovered_date in self._day_cells:
                self._cell_unhighlight(self._hovered_date)
            self._hovered_date = hovered
            if hovered and hovered in self._day_cells:
                self._day_cells[hovered].configure(
                    highlightbackground="#4a8acc", highlightthickness=2)

    def _create_drag_ghost(self, event) -> None:
        todo = next((t for t in self.app.config.todos if t.id == self._drag_id), None)
        if not todo:
            return
        ghost = tk.Toplevel(self.winfo_toplevel())
        ghost.overrideredirect(True)
        ghost.wm_attributes("-topmost", True)
        try:
            ghost.wm_attributes("-alpha", 0.88)
        except Exception:
            pass
        outer = tk.Frame(ghost, bg="#060610", padx=3, pady=3)
        outer.pack()
        body = tk.Frame(outer, bg="#1a1a2e", padx=12, pady=7)
        body.pack()
        # Priority accent
        pri_col = _PRI_COLOR.get(todo.priority, "#7a7a2a")
        tk.Frame(body, bg=pri_col, height=3).pack(fill="x", pady=(0, 5))
        # Text
        tk.Label(body, text=todo.text[:36], bg="#1a1a2e", fg="#f0f0ff",
                 font=("Segoe UI", 11, "bold"), anchor="w").pack(anchor="w")
        # Badges
        info = []
        if todo.category: info.append(f"🏷 {todo.category}")
        ts = _fmt_time(todo)
        if ts:           info.append(f"⏱ {ts}")
        if todo.date:    info.append(f"📅 {_fmt_date_short(todo.date)}")
        if todo.recurrence != "none": info.append("↻")
        if info:
            tk.Label(body, text="  ".join(info), bg="#1a1a2e", fg="#8899bb",
                     font=("Segoe UI", 9)).pack(anchor="w", pady=(3, 0))
        tk.Label(body, text="⟶  Drop on a calendar day",
                 bg="#1a1a2e", fg="#2a3a5a", font=("Segoe UI", 8),
                 ).pack(anchor="w", pady=(5, 0))
        ghost.update_idletasks()
        ghost.geometry(f"+{event.x_root+14}+{event.y_root+10}")
        self._drag_ghost = ghost

    def _on_drag_release(self, event) -> None:
        if not self._drag_id:
            return

        if not self._drag_active:
            # Threshold not reached → treat as a click on badge
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

        if self._hovered_date:
            self._cell_unhighlight(self._hovered_date)
        self._drag_id      = None
        self._drag_source  = None
        self._drag_active  = False
        self._hovered_date = None

    def _cell_at(self, rx: int, ry: int) -> Optional[str]:
        for ds, cell in self._day_cells.items():
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
            cell.configure(highlightbackground="#4a8acc", highlightthickness=2)

    def _cell_leave(self, cell: tk.Frame, ds: str, is_today: bool) -> None:
        if self._drag_id:
            selected = (ds == self._selected_date)
            bdr = "#eeeeee" if selected else (_TODAY_BDR if is_today else "#1e1e38")
            bth = 2 if (selected or is_today) else 1
            cell.configure(highlightbackground=bdr, highlightthickness=bth)

    def _cell_unhighlight(self, ds: str) -> None:
        if ds not in self._day_cells:
            return
        cell     = self._day_cells[ds]
        selected = (ds == self._selected_date)
        try:
            d        = datetime.strptime(ds, "%Y-%m-%d").date()
            is_today = (d == self._today)
        except Exception:
            is_today = False
        bdr = "#eeeeee" if selected else (_TODAY_BDR if is_today else "#1e1e38")
        bth = 2 if (selected or is_today) else 1
        cell.configure(highlightbackground=bdr, highlightthickness=bth)

    # ── keyboard navigation ───────────────────────────────────────────────────

    def _select_date(self, ds: str) -> None:
        prev = self._selected_date
        self._selected_date = ds
        if prev and prev in self._day_cells:
            self._cell_unhighlight(prev)
        if ds in self._day_cells:
            self._day_cells[ds].configure(
                highlightbackground="#eeeeee", highlightthickness=2)

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
        # Navigate calendar if date out of current view
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

    # ── navigation ────────────────────────────────────────────────────────────

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
        self._grid_frame.focus_set()
        today_str = self._today.strftime("%Y-%m-%d")
        if today_str in self._day_cells:
            self._select_date(today_str)

    def _toggle_view(self) -> None:
        self._view_mode = "week" if self._view_mode == "month" else "month"
        self._selected_date = None
        self._refresh_calendar()

    # ── task CRUD ──────────────────────────────────────────────────────────────

    def _add_task(self, preset_date: str = "") -> None:
        dlg = _TodoDialog(self, preset_date=preset_date)
        self.wait_window(dlg)
        if dlg.result:
            dlg.result.color = _next_color(self.app.config.todos)
            self.app.config.todos.append(dlg.result)
            self.app.save_config_only()
            self._refresh_all()

    def _edit_task(self, todo: Todo) -> None:
        dlg = _TodoDialog(self, existing=todo)
        self.wait_window(dlg)
        if dlg.result:
            # copy all fields back
            for field in ("text", "time_type", "duration_mins", "start_time",
                          "end_time", "date", "priority", "category",
                          "recurrence", "recurrence_days", "subtasks"):
                setattr(todo, field, getattr(dlg.result, field))
            self.app.save_config_only()
            self._refresh_all()

    def _delete_task(self, todo: Todo) -> None:
        self.app.config.todos = [t for t in self.app.config.todos if t.id != todo.id]
        self.app.save_config_only()
        self._refresh_all()

    def _toggle_complete(self, todo: Todo) -> None:
        todo.completed = True
        # Auto-generate next recurrence
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

    # ── day popup (toggle) ────────────────────────────────────────────────────

    def _open_day(self, date_str: str) -> None:
        if self._drag_id:
            return
        if self._active_popup is not None:
            try:
                self._active_popup.destroy()
            except Exception:
                pass
            prev = self._active_popup_date
            self._active_popup      = None
            self._active_popup_date = None
            if prev == date_str:
                return
        popup = _DayPopup(self, date_str, self.app)
        self._active_popup      = popup
        self._active_popup_date = date_str

    def _on_popup_closed(self) -> None:
        self._active_popup      = None
        self._active_popup_date = None

    def _refresh_all(self) -> None:
        self._today = date.today()
        self._refresh_task_panel()
        self._refresh_today_strip()
        self._refresh_calendar()


# ── Todo dialog ───────────────────────────────────────────────────────────────

class _TodoDialog(ctk.CTkToplevel):
    def __init__(self, parent, existing: Optional[Todo] = None,
                 preset_date: str = "") -> None:
        super().__init__(parent)
        self.result: Optional[Todo] = None
        self.title("Edit Task" if existing else "New Task")
        self.resizable(True, True)
        self.minsize(480, 400)
        self.wm_attributes("-topmost", True)
        self._existing = existing
        self._parent_tab = parent  # PlannerTab for category access
        self._build(existing, preset_date)
        self.geometry("480x580")
        self.after(120, self.grab_set)
        self.lift()

    def _build(self, ex: Optional[Todo], preset_date: str) -> None:
        pad = {"padx": 18, "pady": 4}

        # ── Save / Cancel pinned at bottom, outside the scroll area ──
        btn_row = ctk.CTkFrame(self, fg_color="transparent")
        btn_row.pack(side="bottom", pady=10)
        ctk.CTkButton(btn_row, text="Save", width=110,
                      command=self._save).pack(side="left", padx=8)
        ctk.CTkButton(btn_row, text="Cancel", width=110,
                      fg_color=("#252535","#252535"),
                      command=self.destroy).pack(side="left", padx=8)

        # ── Scrollable content area ──
        scroll = ctk.CTkScrollableFrame(self, fg_color="transparent")
        scroll.pack(fill="both", expand=True)

        # ── Task text ──
        ctk.CTkLabel(scroll, text="Task:", font=ctk.CTkFont(size=12),
                     anchor="w").pack(fill="x", **pad)
        self._text_var = ctk.StringVar(value=ex.text if ex else "")
        te = ctk.CTkEntry(scroll, textvariable=self._text_var, width=436, height=32)
        te.pack(**pad)
        te.focus_set()
        te.bind("<Return>", lambda _: self._save())

        # ── Priority ──
        ctk.CTkLabel(scroll, text="Priority:", font=ctk.CTkFont(size=12),
                     anchor="w").pack(fill="x", **pad)
        self._priority = ctk.StringVar(value=ex.priority if ex else "medium")
        pri_row = ctk.CTkFrame(scroll, fg_color="transparent")
        pri_row.pack(fill="x", **pad)
        for val, label, col in (("low","Low","#44aa44"),
                                 ("medium","Medium","#aaaa44"),
                                 ("high","High","#cc4444")):
            ctk.CTkRadioButton(pri_row, text=label, variable=self._priority,
                               value=val, text_color=(col, col),
                               ).pack(side="left", padx=10)

        # ── Category ──
        ctk.CTkLabel(scroll, text="Category:", font=ctk.CTkFont(size=12),
                     anchor="w").pack(fill="x", **pad)
        cat_row = ctk.CTkFrame(scroll, fg_color="transparent")
        cat_row.pack(fill="x", **pad)
        cats = ["(none)"] + list(self._parent_tab.app.config.planner_categories)
        self._cat_var = ctk.StringVar(
            value=ex.category if (ex and ex.category) else "(none)")
        self._cat_menu_widget = ctk.CTkOptionMenu(cat_row, variable=self._cat_var,
                              values=cats, width=160, height=28)
        self._cat_menu_widget.pack(side="left", padx=(0, 8))
        ctk.CTkButton(cat_row, text="Manage categories…", width=160, height=28,
                      fg_color=("#1e2a3a","#1e2a3a"),
                      command=self._manage_categories,
                      ).pack(side="left")

        # ── Time ──
        ctk.CTkLabel(scroll, text="Time:", font=ctk.CTkFont(size=12),
                     anchor="w").pack(fill="x", **pad)
        self._time_type = ctk.StringVar(value=ex.time_type if ex else "none")
        radio_row = ctk.CTkFrame(scroll, fg_color="transparent")
        radio_row.pack(fill="x", **pad)
        for val, lbl in (("none","None"),("duration","Duration"),("timespan","Time range")):
            ctk.CTkRadioButton(radio_row, text=lbl, variable=self._time_type,
                               value=val, command=self._update_time_fields,
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

        # ── Date ──
        ctk.CTkLabel(scroll, text="Date (optional):",
                     font=ctk.CTkFont(size=12), anchor="w").pack(fill="x", **pad)
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

        fields = {
            "D": ctk.CTkEntry(date_row, textvariable=self._date_d, width=46, height=28, placeholder_text="DD"),
            "M": ctk.CTkEntry(date_row, textvariable=self._date_m, width=46, height=28, placeholder_text="MM"),
            "Y": ctk.CTkEntry(date_row, textvariable=self._date_y, width=62, height=28, placeholder_text="YYYY"),
        }
        for i, key in enumerate(order):
            fields[key].pack(side="left", padx=2)
            ctk.CTkLabel(date_row, text=sep if i < 2 else "",
                         width=10, text_color="#555577",
                         font=ctk.CTkFont(size=13)).pack(side="left")
        ctk.CTkButton(date_row, text="📅", width=34, height=28,
                      fg_color=("#1e2a3a","#1e2a3a"),
                      command=self._pick_date).pack(side="left", padx=(8,0))
        ctk.CTkLabel(scroll, text=f"Format: {sep.join(order)}",
                     font=ctk.CTkFont(size=10),
                     text_color=("#444466","#444466"), anchor="w",
                     ).pack(fill="x", padx=18)

        # ── Recurrence ──
        ctk.CTkLabel(scroll, text="Recurrence:",
                     font=ctk.CTkFont(size=12), anchor="w").pack(fill="x", **pad)
        self._recurrence = ctk.StringVar(value=ex.recurrence if ex else "none")
        rec_row = ctk.CTkFrame(scroll, fg_color="transparent")
        rec_row.pack(fill="x", **pad)
        for val, lbl in (("none","None"),("daily","Daily"),("weekly","Weekly"),
                          ("monthly","Monthly"),("yearly","Yearly")):
            ctk.CTkRadioButton(rec_row, text=lbl, variable=self._recurrence,
                               value=val, command=self._update_rec_fields,
                               ).pack(side="left", padx=6)
        self._rec_frame = ctk.CTkFrame(scroll, fg_color="transparent")
        self._rec_frame.pack(fill="x", padx=18, pady=(0, 4))
        existing_days = ex.recurrence_days if ex else []
        self._rec_day_vars = {i: tk.BooleanVar(value=i in existing_days)
                               for i in range(7)}
        self._update_rec_fields()

        # ── Subtasks ──
        ctk.CTkLabel(scroll, text="Subtasks:",
                     font=ctk.CTkFont(size=12), anchor="w").pack(fill="x", **pad)
        self._subtask_frame = ctk.CTkFrame(scroll, fg_color="transparent")
        self._subtask_frame.pack(fill="x", padx=18, pady=(0, 4))
        self._subtasks: List[dict] = list(ex.subtasks) if ex else []
        self._rebuild_subtasks()

        sub_add_row = ctk.CTkFrame(scroll, fg_color="transparent")
        sub_add_row.pack(fill="x", padx=18, pady=(0, 8))
        self._new_sub_var = ctk.StringVar()
        sub_e = ctk.CTkEntry(sub_add_row, textvariable=self._new_sub_var,
                              width=310, height=26, placeholder_text="Add subtask…")
        sub_e.pack(side="left", padx=(0, 6))
        sub_e.bind("<Return>", lambda _: self._add_subtask())
        ctk.CTkButton(sub_add_row, text="+ Add", width=70, height=26,
                      command=self._add_subtask).pack(side="left")

    def _update_time_fields(self) -> None:
        for w in self._time_frame.winfo_children():
            w.destroy()
        tt = self._time_type.get()
        if tt == "duration":
            row = ctk.CTkFrame(self._time_frame, fg_color="transparent")
            row.pack(anchor="w")
            for var, unit in ((self._days_var,"d"),(self._hours_var,"h"),(self._mins_var,"m")):
                ctk.CTkEntry(row, textvariable=var, width=52, height=28,
                             placeholder_text="0").pack(side="left", padx=(0,2))
                ctk.CTkLabel(row, text=unit, width=22,
                             font=ctk.CTkFont(size=13, weight="bold"),
                             text_color="#6688cc").pack(side="left", padx=(0,10))
        elif tt == "timespan":
            row = ctk.CTkFrame(self._time_frame, fg_color="transparent")
            row.pack(anchor="w")
            ctk.CTkLabel(row, text="From", width=36, font=ctk.CTkFont(size=11)).pack(side="left")
            ctk.CTkEntry(row, textvariable=self._start_h, width=46, height=28, placeholder_text="HH").pack(side="left")
            ctk.CTkLabel(row, text=":", width=10, font=ctk.CTkFont(size=14, weight="bold"), text_color="#6688cc").pack(side="left")
            ctk.CTkEntry(row, textvariable=self._start_m, width=46, height=28, placeholder_text="MM").pack(side="left", padx=(0,14))
            ctk.CTkLabel(row, text="To", width=24, font=ctk.CTkFont(size=11)).pack(side="left")
            ctk.CTkEntry(row, textvariable=self._end_h, width=46, height=28, placeholder_text="HH").pack(side="left")
            ctk.CTkLabel(row, text=":", width=10, font=ctk.CTkFont(size=14, weight="bold"), text_color="#6688cc").pack(side="left")
            ctk.CTkEntry(row, textvariable=self._end_m, width=46, height=28, placeholder_text="MM").pack(side="left")

    def _update_rec_fields(self) -> None:
        for w in self._rec_frame.winfo_children():
            w.destroy()
        if self._recurrence.get() == "weekly":
            row = ctk.CTkFrame(self._rec_frame, fg_color="transparent")
            row.pack(anchor="w")
            for i, day in enumerate(("Mo","Tu","We","Th","Fr","Sa","Su")):
                ctk.CTkCheckBox(row, text=day, variable=self._rec_day_vars[i],
                                width=46, height=24,
                                checkbox_width=16, checkbox_height=16,
                                ).pack(side="left", padx=2)

    def _pick_date(self) -> None:
        try:
            y = int(self._date_y.get()) if self._date_y.get().strip() else date.today().year
            m = int(self._date_m.get()) if self._date_m.get().strip() else date.today().month
        except ValueError:
            y, m = date.today().year, date.today().month
        _DatePickerPopup(self, y, m, self._set_picked_date)

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
            ctk.CTkCheckBox(row, text=sub["text"], variable=var,
                            command=_chk_changed,
                            checkbox_width=16, checkbox_height=16,
                            ).pack(side="left", fill="x", expand=True)
            ctk.CTkButton(row, text="✕", width=24, height=22,
                          fg_color=("#3a1616","#3a1616"),
                          command=lambda s=sub: self._remove_subtask(s),
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
        dlg = _CategoryManagerDialog(self, self._parent_tab.app)
        self.wait_window(dlg)
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
            color         = self._existing.color if self._existing else "#1e3a5f",
            completed     = self._existing.completed if self._existing else False,
            priority      = self._priority.get(),
            category      = cat,
            recurrence    = self._recurrence.get(),
            recurrence_days = rec_days,
            subtasks      = list(self._subtasks),
        )
        self.destroy()


# ── Date picker ───────────────────────────────────────────────────────────────

class _DatePickerPopup(ctk.CTkToplevel):
    def __init__(self, parent, year: int, month: int, callback) -> None:
        super().__init__(parent)
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
        nav = ctk.CTkFrame(self._body, fg_color="transparent")
        nav.pack(fill="x")
        ctk.CTkButton(nav, text="◀", width=30, height=26, command=self._prev).pack(side="left")
        ctk.CTkLabel(nav, text=f"{calendar.month_name[self._month]} {self._year}",
                     font=ctk.CTkFont(size=12, weight="bold"), width=160).pack(side="left", expand=True)
        ctk.CTkButton(nav, text="▶", width=30, height=26, command=self._next).pack(side="right")

        hf = ctk.CTkFrame(self._body, fg_color="transparent")
        hf.pack(fill="x", pady=(4,0))
        for i, d in enumerate(("Mo","Tu","We","Th","Fr","Sa","Su")):
            fg = "#6688bb" if i < 5 else "#886688"
            ctk.CTkLabel(hf, text=d, width=32, height=22,
                         font=ctk.CTkFont(size=10), text_color=(fg,fg)).grid(row=0, column=i)
            hf.columnconfigure(i, weight=1)

        gf = ctk.CTkFrame(self._body, fg_color="transparent")
        gf.pack(fill="both", expand=True, pady=2)
        for c in range(7): gf.columnconfigure(c, weight=1)

        today = date.today()
        first_wd, days = calendar.monthrange(self._year, self._month)
        row, col = 0, first_wd
        for day_n in range(1, days+1):
            d = date(self._year, self._month, day_n)
            is_today = (d == today)
            ctk.CTkButton(
                gf, text=str(day_n), width=32, height=28,
                fg_color=("#2a5080","#2a5080") if is_today else ("#1e2a3a","#1e2a3a"),
                hover_color=("#3a6090","#3a6090"),
                font=ctk.CTkFont(size=10, weight="bold" if is_today else "normal"),
                command=lambda _d=d: self._select(_d),
            ).grid(row=row, column=col, padx=1, pady=1)
            col += 1
            if col == 7:
                col, row = 0, row+1

    def _prev(self):
        if self._month == 1: self._month, self._year = 12, self._year - 1
        else:                self._month -= 1
        self._render()

    def _next(self):
        if self._month == 12: self._month, self._year = 1, self._year + 1
        else:                 self._month += 1
        self._render()

    def _select(self, d: date):
        self._cb(d)
        self.destroy()


# ── Category manager ──────────────────────────────────────────────────────────

class _CategoryManagerDialog(ctk.CTkToplevel):
    def __init__(self, parent, app: "App") -> None:
        super().__init__(parent)
        self._app = app
        self.title("Manage Categories")
        self.geometry("320x380")
        self.resizable(False, True)
        self.wm_attributes("-topmost", True)
        self._build()
        self.after(100, self.grab_set)
        self.lift()

    def _build(self) -> None:
        ctk.CTkLabel(self, text="Categories",
                     font=ctk.CTkFont(size=14, weight="bold")).pack(pady=(14,4))

        self._list_frame = ctk.CTkScrollableFrame(self, fg_color="transparent")
        self._list_frame.pack(fill="both", expand=True, padx=12)
        self._render_list()

        add_row = ctk.CTkFrame(self, fg_color="transparent")
        add_row.pack(fill="x", padx=12, pady=8)
        self._new_cat_var = ctk.StringVar()
        e = ctk.CTkEntry(add_row, textvariable=self._new_cat_var,
                         placeholder_text="New category name…", height=30)
        e.pack(side="left", fill="x", expand=True, padx=(0,6))
        e.bind("<Return>", lambda _: self._add())
        ctk.CTkButton(add_row, text="+ Add", width=70, height=30,
                      command=self._add).pack(side="left")

        ctk.CTkButton(self, text="Done", width=100,
                      command=self.destroy).pack(pady=(0,12))

    def _render_list(self) -> None:
        for w in self._list_frame.winfo_children():
            w.destroy()
        for i, cat in enumerate(self._app.config.planner_categories):
            row = ctk.CTkFrame(self._list_frame, fg_color="transparent")
            row.pack(fill="x", pady=2)
            dot_col = _CAT_DOTS[i % len(_CAT_DOTS)]
            ctk.CTkLabel(row, text="●", text_color=(dot_col, dot_col),
                         width=20).pack(side="left")
            var = ctk.StringVar(value=cat)
            e = ctk.CTkEntry(row, textvariable=var, height=28)
            e.pack(side="left", fill="x", expand=True, padx=4)
            e.bind("<FocusOut>", lambda ev, v=var, c=cat: self._rename(c, v.get()))
            e.bind("<Return>",   lambda ev, v=var, c=cat: self._rename(c, v.get()))
            ctk.CTkButton(row, text="✕", width=28, height=28,
                          fg_color=("#3a1616","#3a1616"),
                          command=lambda c=cat: self._delete(c)).pack(side="right")

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


# ── Day detail popup ──────────────────────────────────────────────────────────

class _DayPopup(ctk.CTkToplevel):
    def __init__(self, planner: PlannerTab, date_str: str, app: "App") -> None:
        super().__init__(planner)
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
        self.geometry("400x480")
        self.wm_attributes("-topmost", True)
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self._build(title, overdue)
        self.lift()

    def _on_close(self):
        self._planner._on_popup_closed()
        self.destroy()

    def _build(self, title: str, overdue: bool) -> None:
        fg_title = "#cc6644" if overdue else "#99aacc"
        ctk.CTkLabel(self, text=title,
                     font=ctk.CTkFont(size=13, weight="bold"),
                     text_color=(fg_title, fg_title)).pack(padx=16, pady=(12,6))

        scroll = ctk.CTkScrollableFrame(self, fg_color="transparent")
        scroll.pack(fill="both", expand=True, padx=10, pady=4)

        todos = sorted(
            [t for t in self._app.config.todos if t.date == self._date_str],
            key=lambda t: t.start_time or "99:99")

        if not todos:
            ctk.CTkLabel(scroll, text="No tasks for this day.",
                         text_color=("#444466","#444466")).pack(pady=20)
        else:
            for todo in todos:
                self._make_task_row(scroll, todo)

        btn_row = ctk.CTkFrame(self, fg_color="transparent")
        btn_row.pack(pady=8)
        ctk.CTkButton(btn_row, text="+ Add task for this day", width=180,
                      fg_color=("#163a22","#163a22"),
                      command=lambda: (self._on_close(),
                                       self._planner._add_task(self._date_str)),
                      ).pack(side="left", padx=6)
        ctk.CTkButton(btn_row, text="Close", width=80,
                      fg_color=("#252535","#252535"),
                      command=self._on_close).pack(side="left", padx=6)

    def _make_task_row(self, parent, todo: Todo) -> None:
        overdue = _is_overdue(todo)
        bg = ("#1e0808","#1e0808") if overdue else ("#14142a","#14142a")
        row = ctk.CTkFrame(parent, fg_color=bg, corner_radius=6)
        row.pack(fill="x", pady=3)

        top = ctk.CTkFrame(row, fg_color="transparent")
        top.pack(fill="x", padx=8, pady=(6,2))

        pri_col = _PRI_COLOR.get(todo.priority, "#7a7a2a")
        ctk.CTkFrame(top, width=4, height=28, fg_color=(pri_col,pri_col),
                     corner_radius=2).pack(side="left", padx=(0,6), fill="y")

        lbl_text = todo.text
        ts = _fmt_time(todo)
        if ts: lbl_text += f"  [{ts}]"
        ctk.CTkLabel(top, text=lbl_text, anchor="w",
                     font=ctk.CTkFont(size=12),
                     text_color=("#ff8866","#ff8866") if overdue else ("white","white"),
                     ).pack(side="left", fill="x", expand=True)

        if todo.recurrence != "none":
            ctk.CTkLabel(top, text="↻", text_color=("#4a8acc","#4a8acc"),
                         font=ctk.CTkFont(size=11)).pack(side="left")

        # Subtasks
        if todo.subtasks:
            sub_frame = ctk.CTkFrame(row, fg_color="transparent")
            sub_frame.pack(fill="x", padx=20, pady=(0,4))
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
                ctk.CTkCheckBox(sub_row, text=sub["text"], variable=var,
                                command=_sub_toggle,
                                checkbox_width=14, checkbox_height=14,
                                font=ctk.CTkFont(size=11),
                                ).pack(side="left")

        action_row = ctk.CTkFrame(row, fg_color="transparent")
        action_row.pack(fill="x", padx=8, pady=(0,6))
        ctk.CTkButton(action_row, text="Unassign", width=80, height=26,
                      font=ctk.CTkFont(size=10),
                      fg_color=("#2a2a3a","#2a2a3a"),
                      command=lambda t=todo: self._unassign(t),
                      ).pack(side="right", padx=(4,0))
        ctk.CTkButton(action_row, text="Edit", width=60, height=26,
                      font=ctk.CTkFont(size=10),
                      fg_color=("#1e2a3a","#1e2a3a"),
                      command=lambda t=todo: (self._on_close(),
                                              self._planner._edit_task(t)),
                      ).pack(side="right", padx=4)

    def _unassign(self, todo: Todo) -> None:
        todo.date = ""
        self._app.save_config_only()
        self._planner._refresh_all()
        self._on_close()
