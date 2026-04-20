"""
Planner tab  —  monthly calendar + task list.

Layout
──────
  Left panel  (270 px)  :  all tasks (unassigned + assigned), add button
  Right panel (fills)   :  monthly calendar grid

Interactions
────────────
  • "+" button          →  create task dialog
  • ☐ on task row       →  mark complete
  • ✏ on task row       →  edit dialog
  • Drag task           →  drop on calendar day to assign / reassign (stylish ghost)
  • Click calendar day  →  toggle day detail popup (click same day again to close)
  • Mouse wheel on cal  →  navigate months
  • Mouse wheel on list →  scroll tasks
"""
from __future__ import annotations

import calendar
import locale
import tkinter as tk
from datetime import date, datetime
from typing import TYPE_CHECKING, Dict, List, Optional

import customtkinter as ctk

from core.models import Todo

if TYPE_CHECKING:
    from app import App

# ── colour palette ────────────────────────────────────────────────────────────
_PALETTE = [
    "#1e4a6e", "#1e5a3a", "#5a3a1e", "#4a1e5a",
    "#5a1e2a", "#1e4a4a", "#3a4a1e", "#4a3a1e",
]
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
        parts  = []
        if d: parts.append(f"{d}d")
        if h: parts.append(f"{h}h")
        if m: parts.append(f"{m}m")
        return " ".join(parts) or "0m"
    if todo.time_type == "timespan":
        return f"{todo.start_time}–{todo.end_time}"
    return ""


def _fmt_date_short(date_str: str) -> str:
    try:
        d = datetime.strptime(date_str, "%Y-%m-%d").date()
        return d.strftime("%b %d")
    except Exception:
        return date_str


def _locale_date_order():
    """Return (order_str, sep) based on system locale.
    order_str is one of 'DMY', 'MDY', 'YMD'.
    """
    try:
        lc = locale.getlocale()[0] or ""
        if lc.startswith(("de_", "fr_", "nl_", "pl_", "cs_", "sk_", "hu_",
                           "it_", "es_", "pt_", "tr_", "ro_", "hr_")):
            return "DMY", "."
        if lc.startswith(("en_US", "en_CA", "en_PH")):
            return "MDY", "/"
        if lc.startswith(("zh_", "ja_", "ko_")):
            return "YMD", "-"
    except Exception:
        pass
    return "DMY", "."


# ── main widget ───────────────────────────────────────────────────────────────

class PlannerTab(ctk.CTkFrame):
    def __init__(self, parent: ctk.CTkBaseClass, app: "App") -> None:
        super().__init__(parent, fg_color="transparent")
        self.app = app
        self._today      = date.today()
        self._view_year  = self._today.year
        self._view_month = self._today.month
        self._day_cells: Dict[str, tk.Frame] = {}
        self._drag_id:   Optional[str] = None
        self._drag_ghost: Optional[tk.Toplevel] = None
        self._hovered_date: Optional[str] = None
        # Day popup toggle
        self._active_popup: Optional[_DayPopup] = None
        self._active_popup_date: Optional[str]  = None

        self._build()
        self._refresh_all()

    # ── layout ────────────────────────────────────────────────────────────────

    def _build(self) -> None:
        self._left = tk.Frame(self, bg=_PANEL_BG, width=270)
        self._left.pack(side="left", fill="y")
        self._left.pack_propagate(False)

        tk.Frame(self, width=1, bg="#1e1e38").pack(side="left", fill="y")

        self._right = tk.Frame(self, bg=_HEADER_BG)
        self._right.pack(side="left", fill="both", expand=True)

        self._build_task_panel()
        self._build_calendar()

        self.winfo_toplevel().bind("<B1-Motion>",       self._on_drag_motion,  add="+")
        self.winfo_toplevel().bind("<ButtonRelease-1>", self._on_drag_release, add="+")

    # ── task panel ────────────────────────────────────────────────────────────

    def _build_task_panel(self) -> None:
        hdr = tk.Frame(self._left, bg=_HEADER_BG, height=46)
        hdr.pack(fill="x")
        hdr.pack_propagate(False)

        tk.Label(hdr, text="Tasks", bg=_HEADER_BG, fg="#99aacc",
                 font=("Segoe UI", 13, "bold")).pack(side="left", padx=12, pady=10)

        tk.Button(hdr, text="+ Add", command=self._add_task,
                  bg="#163a22", fg="#aaddaa", activebackground="#1e4a2a",
                  activeforeground="#ccffcc", relief="flat",
                  font=("Segoe UI", 10), cursor="hand2", padx=8,
                  ).pack(side="right", padx=8, pady=8)

        tk.Label(self._left, text="☐ = mark done   ✏ = edit   drag = assign to day",
                 bg=_PANEL_BG, fg="#333355", font=("Segoe UI", 8),
                 ).pack(fill="x", padx=8, pady=(2, 4))

        # Canvas + inner frame for scrollable task list
        self._task_canvas = tk.Canvas(self._left, bg=_PANEL_BG, highlightthickness=0)
        self._task_canvas.pack(side="left", fill="both", expand=True)

        vsb = tk.Scrollbar(self._left, orient="vertical",
                           command=self._task_canvas.yview,
                           bg=_PANEL_BG, troughcolor="#0a0a16",
                           activebackground="#252540")
        vsb.pack(side="right", fill="y")
        self._task_canvas.configure(yscrollcommand=vsb.set)

        self._task_inner = tk.Frame(self._task_canvas, bg=_PANEL_BG)
        self._task_canvas_win = self._task_canvas.create_window(
            (0, 0), window=self._task_inner, anchor="nw")

        self._task_inner.bind("<Configure>", self._on_task_frame_resize)
        self._task_canvas.bind("<Configure>", self._on_canvas_resize)
        for ev in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
            self._task_canvas.bind(ev, self._on_task_scroll)
            self._task_inner.bind(ev, self._on_task_scroll)

    def _on_task_frame_resize(self, _event=None) -> None:
        self._task_canvas.configure(scrollregion=self._task_canvas.bbox("all"))

    def _on_canvas_resize(self, event) -> None:
        self._task_canvas.itemconfig(self._task_canvas_win, width=event.width)

    def _on_task_scroll(self, event) -> None:
        if event.num == 4:
            self._task_canvas.yview_scroll(-1, "units")
        elif event.num == 5:
            self._task_canvas.yview_scroll(1, "units")
        else:
            self._task_canvas.yview_scroll(int(-event.delta / 120), "units")

    def _bind_scroll(self, w: tk.Widget) -> None:
        for ev in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
            w.bind(ev, self._on_task_scroll, add="+")

    def _refresh_task_panel(self) -> None:
        for w in self._task_inner.winfo_children():
            w.destroy()

        active = [t for t in self.app.config.todos if not t.completed]

        if not active:
            lbl = tk.Label(self._task_inner, text="No tasks yet. Press + Add.",
                           bg=_PANEL_BG, fg="#333355", font=("Segoe UI", 10))
            lbl.pack(pady=20)
            self._bind_scroll(lbl)
            return

        for todo in active:
            row = self._make_task_row(self._task_inner, todo)
            self._bind_scroll(row)
            for child in row.winfo_children():
                self._bind_scroll(child)
                for gc in child.winfo_children():
                    self._bind_scroll(gc)

        self._task_inner.update_idletasks()
        self._task_canvas.configure(scrollregion=self._task_canvas.bbox("all"))

    def _make_task_row(self, parent, todo: Todo) -> tk.Frame:
        assigned = bool(todo.date)
        row_bg   = "#10101e" if assigned else "#14142a"

        row = tk.Frame(parent, bg=todo.color, cursor="fleur")
        row.pack(fill="x", pady=2, padx=2)

        # Left colour accent bar
        tk.Frame(row, width=5, bg=todo.color).pack(side="left", fill="y")

        inner = tk.Frame(row, bg=row_bg)
        inner.pack(side="left", fill="both", expand=True)

        # Checkbox button: ☐ / ☑
        chk_sym = "☑" if todo.completed else "☐"
        chk_fg  = "#55cc55" if todo.completed else "#8899bb"
        tk.Button(
            inner, text=chk_sym,
            command=lambda t=todo: self._toggle_complete(t),
            bg=row_bg, fg=chk_fg, activebackground=row_bg,
            activeforeground="#88ff88",
            relief="flat", font=("Segoe UI", 13), cursor="hand2", bd=0, padx=2,
        ).pack(side="left", padx=(4, 0), pady=2)

        # Task text
        display = todo.text if len(todo.text) <= 24 else todo.text[:22] + "…"
        txt_fg  = "#666677" if assigned else "#c8c8e8"
        lbl = tk.Label(inner, text=display, bg=row_bg, fg=txt_fg,
                       font=("Segoe UI", 10), anchor="w")
        lbl.pack(side="left", padx=4, pady=4)

        # Date badge for assigned tasks
        if assigned:
            tk.Label(inner, text=f"📅 {_fmt_date_short(todo.date)}",
                     bg=row_bg, fg="#4a6a99", font=("Segoe UI", 8),
                     ).pack(side="left", padx=2)

        # Time badge
        time_str = _fmt_time(todo)
        if time_str:
            tk.Label(inner, text=time_str, bg=row_bg, fg="#7788aa",
                     font=("Segoe UI", 8)).pack(side="left")

        # Edit / Delete buttons
        btn_f = tk.Frame(inner, bg=row_bg)
        btn_f.pack(side="right", padx=2)
        tk.Button(btn_f, text="✏",
                  command=lambda t=todo: self._edit_task(t),
                  bg=row_bg, fg="#6688bb", activebackground="#1e2a3a",
                  relief="flat", font=("Segoe UI", 10), cursor="hand2",
                  ).pack(side="left")
        tk.Button(btn_f, text="✕",
                  command=lambda t=todo: self._delete_task(t),
                  bg=row_bg, fg="#885555", activebackground="#3a1616",
                  relief="flat", font=("Segoe UI", 10), cursor="hand2",
                  ).pack(side="left")

        for w in (row, lbl, inner):
            w.bind("<ButtonPress-1>", lambda e, tid=todo.id: self._drag_start(tid, e))

        return row

    def _toggle_complete(self, todo: Todo) -> None:
        todo.completed = not todo.completed
        self.app.save_config_only()
        self._refresh_all()

    # ── calendar ──────────────────────────────────────────────────────────────

    def _build_calendar(self) -> None:
        nav = tk.Frame(self._right, bg=_HEADER_BG, height=46)
        nav.pack(fill="x")
        nav.pack_propagate(False)

        tk.Button(nav, text="◀", command=self._prev_month,
                  bg=_HEADER_BG, fg="#9999bb", activebackground="#1e1e38",
                  relief="flat", font=("Segoe UI", 13), width=2, cursor="hand2",
                  ).pack(side="left", padx=10, pady=8)

        self._month_lbl = tk.Label(nav, text="", bg=_HEADER_BG, fg="#c8c8f0",
                                   font=("Segoe UI", 14, "bold"), width=18)
        self._month_lbl.pack(side="left", padx=6)

        tk.Button(nav, text="▶", command=self._next_month,
                  bg=_HEADER_BG, fg="#9999bb", activebackground="#1e1e38",
                  relief="flat", font=("Segoe UI", 13), width=2, cursor="hand2",
                  ).pack(side="left", padx=4)

        tk.Button(nav, text="Today", command=self._go_today,
                  bg="#1e2a3a", fg="#8899bb", activebackground="#2a3a4a",
                  relief="flat", font=("Segoe UI", 10), cursor="hand2", padx=8,
                  ).pack(side="right", padx=12, pady=10)

        dow_frame = tk.Frame(self._right, bg=_HEADER_BG)
        dow_frame.pack(fill="x")
        for i, day in enumerate(("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")):
            fg = "#6688bb" if i < 5 else "#886688"
            tk.Label(dow_frame, text=day, bg=_HEADER_BG, fg=fg,
                     font=("Segoe UI", 10, "bold"),
                     ).grid(row=0, column=i, sticky="ew", padx=2, pady=4)
            dow_frame.columnconfigure(i, weight=1)

        self._grid_frame = tk.Frame(self._right, bg="#0a0a18")
        self._grid_frame.pack(fill="both", expand=True, padx=6, pady=(0, 6))
        for c in range(7):
            self._grid_frame.columnconfigure(c, weight=1)

        # Mouse wheel on calendar grid navigates months
        self._grid_frame.bind("<MouseWheel>", self._on_cal_scroll)
        self._grid_frame.bind("<Button-4>",   self._on_cal_scroll)
        self._grid_frame.bind("<Button-5>",   self._on_cal_scroll)

    def _on_cal_scroll(self, event) -> None:
        if event.num == 4 or (hasattr(event, "delta") and event.delta > 0):
            self._prev_month()
        else:
            self._next_month()

    def _refresh_calendar(self) -> None:
        for w in self._grid_frame.winfo_children():
            w.destroy()
        self._day_cells.clear()

        yr, mo = self._view_year, self._view_month
        self._month_lbl.config(text=f"{calendar.month_name[mo]}  {yr}")

        first_wd, days_in_month = calendar.monthrange(yr, mo)
        from datetime import timedelta
        first_date = date(yr, mo, 1)

        row, col = 0, first_wd
        for r in range(6):
            self._grid_frame.rowconfigure(r, weight=1, minsize=80)

        for c in range(first_wd):
            pad_date = first_date - timedelta(days=first_wd - c)
            self._make_day_cell(row, c, pad_date, other_month=True)

        for day_num in range(1, days_in_month + 1):
            d = date(yr, mo, day_num)
            self._make_day_cell(row, col, d, other_month=False)
            col += 1
            if col == 7:
                col = 0
                row += 1

        extra = 0
        while col < 7 and row < 6:
            pad_date = date(yr, mo, days_in_month) + timedelta(days=extra + 1)
            extra += 1
            self._make_day_cell(row, col, pad_date, other_month=True)
            col += 1
            if col == 7:
                col = 0
                row += 1

    def _make_day_cell(self, row: int, col: int,
                       d: date, other_month: bool) -> None:
        is_today  = (d == self._today)
        date_str  = d.strftime("%Y-%m-%d")
        todos_day = [t for t in self.app.config.todos
                     if t.date == date_str and not t.completed]

        bg   = _TODAY_BG if is_today else ("#0c0c1a" if other_month else _CELL_BG)
        cell = tk.Frame(self._grid_frame, bg=bg,
                        highlightthickness=2 if is_today else 1,
                        highlightbackground=_TODAY_BDR if is_today else "#1e1e38",
                        cursor="hand2")
        cell.grid(row=row, column=col, sticky="nsew", padx=2, pady=2)
        self._day_cells[date_str] = cell

        # Propagate mousewheel to month navigation
        for ev in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
            cell.bind(ev, self._on_cal_scroll, add="+")

        num_fg  = _TODAY_BDR if is_today else ("#444455" if other_month else "#8888aa")
        num_lbl = tk.Label(cell, text=str(d.day), bg=bg, fg=num_fg,
                           font=("Segoe UI", 10, "bold" if is_today else "normal"),
                           anchor="ne")
        num_lbl.pack(fill="x", padx=4, pady=(3, 0))
        num_lbl.bind(ev, self._on_cal_scroll, add="+")  # last ev = Button-5, fine

        for todo in todos_day[:3]:
            badge = tk.Frame(cell, bg=todo.color, height=18)
            badge.pack(fill="x", padx=3, pady=1)
            badge.pack_propagate(False)
            t = todo.text[:22] + "…" if len(todo.text) > 22 else todo.text
            tk.Label(badge, text=t, bg=todo.color, fg="#e8e8ff",
                     font=("Segoe UI", 8), anchor="w").pack(fill="x", padx=3)

        if len(todos_day) > 3:
            tk.Label(cell, text=f"+{len(todos_day)-3} more",
                     bg=bg, fg="#555577", font=("Segoe UI", 8),
                     ).pack(anchor="w", padx=4)

        # Bind click on every widget inside the cell so clicking a badge still opens the popup
        self._bind_cell_click(cell, date_str)

        def _enter(e, c=cell):
            if self._drag_id:
                c.configure(highlightbackground="#4a8acc", highlightthickness=2)

        def _leave(e, c=cell, it=is_today):
            if self._drag_id:
                c.configure(highlightbackground=_TODAY_BDR if it else "#1e1e38",
                            highlightthickness=2 if it else 1)

        cell.bind("<Enter>", _enter)
        cell.bind("<Leave>", _leave)

    def _bind_cell_click(self, widget: tk.Widget, date_str: str) -> None:
        """Recursively bind <Button-1> on widget and all its descendants."""
        widget.bind("<Button-1>", lambda e, ds=date_str: self._open_day(ds))
        for child in widget.winfo_children():
            self._bind_cell_click(child, date_str)

    # ── drag and drop ──────────────────────────────────────────────────────────

    def _drag_start(self, todo_id: str, event) -> None:
        self._drag_id = todo_id
        todo = next((t for t in self.app.config.todos if t.id == todo_id), None)
        if not todo:
            return

        # Stylish semi-transparent ghost as a borderless Toplevel
        ghost = tk.Toplevel(self.winfo_toplevel())
        ghost.overrideredirect(True)
        ghost.wm_attributes("-topmost", True)
        try:
            ghost.wm_attributes("-alpha", 0.88)
        except Exception:
            pass

        # Outer shadow border
        outer = tk.Frame(ghost, bg="#060610", padx=3, pady=3)
        outer.pack()

        # Coloured header strip + inner body
        body = tk.Frame(outer, bg="#1a1a2e", padx=14, pady=8)
        body.pack()

        # Top accent line in task colour
        tk.Frame(body, bg=todo.color, height=3).pack(fill="x", pady=(0, 6))

        # Task text
        tk.Label(body, text=todo.text[:38], bg="#1a1a2e", fg="#f0f0ff",
                 font=("Segoe UI", 11, "bold"), anchor="w").pack(anchor="w")

        # Time badge
        time_str = _fmt_time(todo)
        if time_str:
            tk.Label(body, text=f"⏱  {time_str}", bg="#1a1a2e", fg="#8899bb",
                     font=("Segoe UI", 9)).pack(anchor="w", pady=(3, 0))

        # Date badge if assigned
        if todo.date:
            tk.Label(body, text=f"📅  {_fmt_date_short(todo.date)}",
                     bg="#1a1a2e", fg="#4a7aaa", font=("Segoe UI", 9),
                     ).pack(anchor="w")

        # Drop hint
        tk.Label(body, text="⟶  Drop on a calendar day",
                 bg="#1a1a2e", fg="#2a3a5a", font=("Segoe UI", 8),
                 ).pack(anchor="w", pady=(6, 0))

        ghost.update_idletasks()
        ghost.geometry(f"+{event.x_root + 14}+{event.y_root + 10}")
        self._drag_ghost = ghost

    def _on_drag_motion(self, event) -> None:
        if not self._drag_id or not self._drag_ghost:
            return
        self._drag_ghost.geometry(f"+{event.x_root + 14}+{event.y_root + 10}")
        hovered = self._cell_at(event.x_root, event.y_root)
        if hovered != self._hovered_date:
            if self._hovered_date and self._hovered_date in self._day_cells:
                c  = self._day_cells[self._hovered_date]
                it = (self._hovered_date == self._today.strftime("%Y-%m-%d"))
                c.configure(highlightbackground=_TODAY_BDR if it else "#1e1e38",
                            highlightthickness=2 if it else 1)
            self._hovered_date = hovered
            if hovered and hovered in self._day_cells:
                self._day_cells[hovered].configure(
                    highlightbackground="#4a8acc", highlightthickness=2)

    def _on_drag_release(self, event) -> None:
        if not self._drag_id:
            return
        if self._drag_ghost:
            self._drag_ghost.destroy()
            self._drag_ghost = None

        target = self._cell_at(event.x_root, event.y_root)
        if target:
            todo = next((t for t in self.app.config.todos
                         if t.id == self._drag_id), None)
            if todo:
                todo.date = target
                self.app.save_config_only()
                self._refresh_all()

        if self._hovered_date and self._hovered_date in self._day_cells:
            c  = self._day_cells[self._hovered_date]
            it = (self._hovered_date == self._today.strftime("%Y-%m-%d"))
            c.configure(highlightbackground=_TODAY_BDR if it else "#1e1e38",
                        highlightthickness=2 if it else 1)
        self._drag_id      = None
        self._hovered_date = None

    def _cell_at(self, rx: int, ry: int) -> Optional[str]:
        for date_str, cell in self._day_cells.items():
            try:
                x, y = cell.winfo_rootx(), cell.winfo_rooty()
                w, h = cell.winfo_width(), cell.winfo_height()
                if x <= rx < x + w and y <= ry < y + h:
                    return date_str
            except Exception:
                pass
        return None

    # ── navigation ────────────────────────────────────────────────────────────

    def _prev_month(self) -> None:
        if self._view_month == 1:
            self._view_month, self._view_year = 12, self._view_year - 1
        else:
            self._view_month -= 1
        self._refresh_calendar()

    def _next_month(self) -> None:
        if self._view_month == 12:
            self._view_month, self._view_year = 1, self._view_year + 1
        else:
            self._view_month += 1
        self._refresh_calendar()

    def _go_today(self) -> None:
        self._today = date.today()
        self._view_year, self._view_month = self._today.year, self._today.month
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
            todo.text          = dlg.result.text
            todo.time_type     = dlg.result.time_type
            todo.duration_mins = dlg.result.duration_mins
            todo.start_time    = dlg.result.start_time
            todo.end_time      = dlg.result.end_time
            todo.date          = dlg.result.date
            self.app.save_config_only()
            self._refresh_all()

    def _delete_task(self, todo: Todo) -> None:
        self.app.config.todos = [t for t in self.app.config.todos if t.id != todo.id]
        self.app.save_config_only()
        self._refresh_all()

    # ── day detail popup (toggle) ─────────────────────────────────────────────

    def _open_day(self, date_str: str) -> None:
        if self._drag_id:
            return
        # Toggle: if same day popup is already open, close it
        if self._active_popup is not None:
            try:
                self._active_popup.destroy()
            except Exception:
                pass
            prev = self._active_popup_date
            self._active_popup      = None
            self._active_popup_date = None
            if prev == date_str:   # same day → just close
                return
        # Open new popup
        popup = _DayPopup(self, date_str, self.app)
        self._active_popup      = popup
        self._active_popup_date = date_str

    def _on_popup_closed(self) -> None:
        self._active_popup      = None
        self._active_popup_date = None

    def _refresh_all(self) -> None:
        self._refresh_task_panel()
        self._refresh_calendar()


# ── Todo dialog ───────────────────────────────────────────────────────────────

class _TodoDialog(ctk.CTkToplevel):
    def __init__(self, parent, existing: Optional[Todo] = None,
                 preset_date: str = "") -> None:
        super().__init__(parent)
        self.result: Optional[Todo] = None
        self.title("Edit Task" if existing else "New Task")
        self.resizable(False, True)
        self.wm_attributes("-topmost", True)
        self._existing = existing
        self._build(existing, preset_date)
        self.update_idletasks()
        self.geometry(f"460x{max(self.winfo_reqheight() + 24, 400)}")
        self.after(120, self.grab_set)
        self.lift()

    def _build(self, ex: Optional[Todo], preset_date: str) -> None:
        pad = {"padx": 18, "pady": 5}

        # ── Task text ──
        ctk.CTkLabel(self, text="Task:", font=ctk.CTkFont(size=12),
                     anchor="w").pack(fill="x", **pad)
        self._text_var = ctk.StringVar(value=ex.text if ex else "")
        te = ctk.CTkEntry(self, textvariable=self._text_var, width=416, height=32)
        te.pack(**pad)
        te.focus_set()
        te.bind("<Return>", lambda _: self._save())

        # ── Time type radios ──
        ctk.CTkLabel(self, text="Time:", font=ctk.CTkFont(size=12),
                     anchor="w").pack(fill="x", **pad)
        self._time_type = ctk.StringVar(value=ex.time_type if ex else "none")
        radio_row = ctk.CTkFrame(self, fg_color="transparent")
        radio_row.pack(fill="x", **pad)
        for val, lbl in (("none", "None"), ("duration", "Duration"),
                         ("timespan", "Time range")):
            ctk.CTkRadioButton(radio_row, text=lbl, variable=self._time_type,
                               value=val, command=self._update_time_fields,
                               ).pack(side="left", padx=10)

        # ── Duration vars (d / h / m) ──
        ex_total = ex.duration_mins if ex else 0
        ex_days, rem = divmod(ex_total, 1440)
        ex_hours, ex_mins = divmod(rem, 60)
        self._days_var  = ctk.StringVar(value=str(ex_days)  if ex_days  else "")
        self._hours_var = ctk.StringVar(value=str(ex_hours) if ex_hours else "")
        self._mins_var  = ctk.StringVar(value=str(ex_mins)  if ex_mins  else "")

        # ── Timespan vars (HH, MM for start & end) ──
        start = ex.start_time if ex else ""
        end   = ex.end_time   if ex else ""
        s_h, s_m = (start.split(":") + [""])[:2] if ":" in start else ("", "")
        e_h, e_m = (end.split(":") + [""])[:2]   if ":" in end   else ("", "")
        self._start_h = ctk.StringVar(value=s_h)
        self._start_m = ctk.StringVar(value=s_m)
        self._end_h   = ctk.StringVar(value=e_h)
        self._end_m   = ctk.StringVar(value=e_m)

        # ── Time fields container ──
        self._time_frame = ctk.CTkFrame(self, fg_color="transparent")
        self._time_frame.pack(fill="x", padx=18, pady=(0, 4))
        self._update_time_fields()

        # ── Date picker ──
        ctk.CTkLabel(self, text="Date (optional):",
                     font=ctk.CTkFont(size=12), anchor="w").pack(fill="x", **pad)

        date_row = ctk.CTkFrame(self, fg_color="transparent")
        date_row.pack(fill="x", **pad)

        order, sep = _locale_date_order()
        # Parse existing date into components
        ex_date = ex.date if ex else preset_date or ""
        try:
            _d = datetime.strptime(ex_date, "%Y-%m-%d").date() if ex_date else None
        except ValueError:
            _d = None

        self._date_d = ctk.StringVar(value=str(_d.day)   if _d else "")
        self._date_m = ctk.StringVar(value=str(_d.month) if _d else "")
        self._date_y = ctk.StringVar(value=str(_d.year)  if _d else "")

        def _int_entry(var, ph, w=46):
            e = ctk.CTkEntry(date_row, textvariable=var, width=w, height=28,
                             placeholder_text=ph)
            return e

        def _sep_lbl(t):
            ctk.CTkLabel(date_row, text=t, width=14,
                         font=ctk.CTkFont(size=13), text_color="#555577",
                         ).pack(side="left")

        # Order the day/month/year fields according to locale
        fields = {
            "D": (_int_entry(self._date_d, "DD"), "D"),
            "M": (_int_entry(self._date_m, "MM"), "M"),
            "Y": (_int_entry(self._date_y, "YYYY", w=60), "Y"),
        }
        for i, key in enumerate(order):
            fields[key][0].pack(side="left", padx=2)
            ctk.CTkLabel(date_row, text=sep if i < 2 else "",
                         width=10, text_color="#555577",
                         font=ctk.CTkFont(size=13)).pack(side="left")

        ctk.CTkButton(
            date_row, text="📅", width=34, height=28,
            fg_color=("#1e2a3a", "#1e2a3a"),
            hover_color=("#2a3a4a", "#2a3a4a"),
            command=self._pick_date,
        ).pack(side="left", padx=(8, 0))

        # Hint label showing date order
        order_str = sep.join(order)   # e.g. "D.M.Y"
        ctk.CTkLabel(self, text=f"Format: {order_str}",
                     font=ctk.CTkFont(size=10),
                     text_color=("#444466", "#444466"),
                     anchor="w").pack(fill="x", padx=18)

        # ── Save / Cancel ──
        btn_row = ctk.CTkFrame(self, fg_color="transparent")
        btn_row.pack(pady=14)
        ctk.CTkButton(btn_row, text="Save", width=110,
                      command=self._save).pack(side="left", padx=8)
        ctk.CTkButton(btn_row, text="Cancel", width=110,
                      fg_color=("#252535", "#252535"),
                      command=self.destroy).pack(side="left", padx=8)

    # ── Time fields update ────────────────────────────────────────────────────

    def _update_time_fields(self) -> None:
        for w in self._time_frame.winfo_children():
            w.destroy()
        tt = self._time_type.get()

        if tt == "duration":
            # Three labelled inputs: [__] d   [__] h   [__] m
            row = ctk.CTkFrame(self._time_frame, fg_color="transparent")
            row.pack(fill="x", anchor="w")
            for var, unit, ph, w in [
                (self._days_var,  "d", "0", 52),
                (self._hours_var, "h", "0", 52),
                (self._mins_var,  "m", "0", 52),
            ]:
                ctk.CTkEntry(row, textvariable=var, width=w, height=28,
                             placeholder_text=ph).pack(side="left", padx=(0, 2))
                ctk.CTkLabel(row, text=unit, width=22,
                             font=ctk.CTkFont(size=13, weight="bold"),
                             text_color="#6688cc").pack(side="left", padx=(0, 10))

        elif tt == "timespan":
            # From [HH] : [MM]   To [HH] : [MM]
            row = ctk.CTkFrame(self._time_frame, fg_color="transparent")
            row.pack(fill="x", anchor="w")
            ctk.CTkLabel(row, text="From", width=38,
                         font=ctk.CTkFont(size=11)).pack(side="left", padx=(0, 4))
            ctk.CTkEntry(row, textvariable=self._start_h, width=46, height=28,
                         placeholder_text="HH").pack(side="left")
            ctk.CTkLabel(row, text=":", width=10,
                         font=ctk.CTkFont(size=14, weight="bold"),
                         text_color="#6688cc").pack(side="left")
            ctk.CTkEntry(row, textvariable=self._start_m, width=46, height=28,
                         placeholder_text="MM").pack(side="left", padx=(0, 16))
            ctk.CTkLabel(row, text="To", width=24,
                         font=ctk.CTkFont(size=11)).pack(side="left", padx=(0, 4))
            ctk.CTkEntry(row, textvariable=self._end_h, width=46, height=28,
                         placeholder_text="HH").pack(side="left")
            ctk.CTkLabel(row, text=":", width=10,
                         font=ctk.CTkFont(size=14, weight="bold"),
                         text_color="#6688cc").pack(side="left")
            ctk.CTkEntry(row, textvariable=self._end_m, width=46, height=28,
                         placeholder_text="MM").pack(side="left")

    # ── Date picker popup ─────────────────────────────────────────────────────

    def _pick_date(self) -> None:
        try:
            y = int(self._date_y.get()) if self._date_y.get().strip() else self._today_val().year
            m = int(self._date_m.get()) if self._date_m.get().strip() else self._today_val().month
        except ValueError:
            y, m = self._today_val().year, self._today_val().month
        _DatePickerPopup(self, y, m, self._set_picked_date)

    def _today_val(self) -> date:
        return date.today()

    def _set_picked_date(self, d: date) -> None:
        self._date_d.set(str(d.day))
        self._date_m.set(str(d.month))
        self._date_y.set(str(d.year))

    # ── Save ──────────────────────────────────────────────────────────────────

    def _save(self) -> None:
        text = self._text_var.get().strip()
        if not text:
            return
        tt = self._time_type.get()

        # Duration: d/h/m → total minutes
        dur = 0
        if tt == "duration":
            try:
                dur = (int(self._days_var.get()  or 0) * 1440 +
                       int(self._hours_var.get() or 0) * 60  +
                       int(self._mins_var.get()  or 0))
            except ValueError:
                dur = 0

        # Timespan: build "HH:MM" strings
        start_str = end_str = ""
        if tt == "timespan":
            try:
                sh = int(self._start_h.get() or 0)
                sm = int(self._start_m.get() or 0)
                eh = int(self._end_h.get()   or 0)
                em = int(self._end_m.get()   or 0)
                start_str = f"{sh:02d}:{sm:02d}"
                end_str   = f"{eh:02d}:{em:02d}"
            except ValueError:
                pass

        # Date: compose from D/M/Y fields
        date_val = ""
        try:
            dv = self._date_d.get().strip()
            mv = self._date_m.get().strip()
            yv = self._date_y.get().strip()
            if dv and mv and yv:
                parsed = date(int(yv), int(mv), int(dv))
                date_val = parsed.strftime("%Y-%m-%d")
        except (ValueError, TypeError):
            pass

        import uuid as _uuid
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
        )
        self.destroy()


# ── Mini date-picker popup ────────────────────────────────────────────────────

class _DatePickerPopup(ctk.CTkToplevel):
    def __init__(self, parent, year: int, month: int,
                 callback) -> None:
        super().__init__(parent)
        self._callback = callback
        self._year  = year
        self._month = month
        self.title("Pick a date")
        self.resizable(False, False)
        self.wm_attributes("-topmost", True)
        self._build()
        self.update_idletasks()
        self.after(80, self.grab_set)
        self.lift()

    def _build(self) -> None:
        self._body = ctk.CTkFrame(self, fg_color="transparent")
        self._body.pack(fill="both", expand=True, padx=8, pady=8)
        self._render()

    def _render(self) -> None:
        for w in self._body.winfo_children():
            w.destroy()

        # Navigation
        nav = ctk.CTkFrame(self._body, fg_color="transparent")
        nav.pack(fill="x")
        ctk.CTkButton(nav, text="◀", width=30, height=26,
                      command=self._prev).pack(side="left")
        ctk.CTkLabel(nav, text=f"{calendar.month_name[self._month]} {self._year}",
                     font=ctk.CTkFont(size=12, weight="bold"),
                     width=150).pack(side="left", expand=True)
        ctk.CTkButton(nav, text="▶", width=30, height=26,
                      command=self._next).pack(side="right")

        # Day headers
        hf = ctk.CTkFrame(self._body, fg_color="transparent")
        hf.pack(fill="x", pady=(4, 0))
        for i, d in enumerate(("Mo", "Tu", "We", "Th", "Fr", "Sa", "Su")):
            fg = "#6688bb" if i < 5 else "#886688"
            ctk.CTkLabel(hf, text=d, width=32, height=22,
                         font=ctk.CTkFont(size=10),
                         text_color=(fg, fg)).grid(row=0, column=i)
            hf.columnconfigure(i, weight=1)

        # Grid
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
            fg_color = ("#2a5080", "#2a5080") if is_today else ("#1e2a3a", "#1e2a3a")
            btn = ctk.CTkButton(
                gf, text=str(day_n), width=32, height=28,
                fg_color=fg_color,
                hover_color=("#3a6090", "#3a6090"),
                font=ctk.CTkFont(size=10, weight="bold" if is_today else "normal"),
                command=lambda _d=d: self._select(_d),
            )
            btn.grid(row=row, column=col, padx=1, pady=1)
            col += 1
            if col == 7:
                col = 0
                row += 1

    def _prev(self) -> None:
        if self._month == 1:
            self._month, self._year = 12, self._year - 1
        else:
            self._month -= 1
        self._render()

    def _next(self) -> None:
        if self._month == 12:
            self._month, self._year = 1, self._year + 1
        else:
            self._month += 1
        self._render()

    def _select(self, d: date) -> None:
        self._callback(d)
        self.destroy()


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
        except Exception:
            title = date_str
        self.title(title)
        self.geometry("380x420")
        self.wm_attributes("-topmost", True)
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self._build(title)
        self.lift()

    def _on_close(self) -> None:
        self._planner._on_popup_closed()
        self.destroy()

    def _build(self, title: str) -> None:
        ctk.CTkLabel(self, text=title,
                     font=ctk.CTkFont(size=14, weight="bold"),
                     text_color=("#99aacc", "#99aacc"),
                     ).pack(padx=16, pady=(14, 6))

        scroll = ctk.CTkScrollableFrame(self, fg_color="transparent")
        scroll.pack(fill="both", expand=True, padx=10, pady=4)

        todos = [t for t in self._app.config.todos if t.date == self._date_str]

        if not todos:
            ctk.CTkLabel(scroll, text="No tasks for this day.",
                         text_color=("#444466", "#444466"),
                         ).pack(pady=20)
        else:
            for todo in todos:
                self._make_row(scroll, todo)

        btn_row = ctk.CTkFrame(self, fg_color="transparent")
        btn_row.pack(pady=8)
        ctk.CTkButton(btn_row, text="+ Add task for this day", width=180,
                      fg_color=("#163a22", "#163a22"),
                      command=lambda: (self._on_close(),
                                       self._planner._add_task(self._date_str)),
                      ).pack(side="left", padx=6)
        ctk.CTkButton(btn_row, text="Close", width=80,
                      fg_color=("#252535", "#252535"),
                      command=self._on_close).pack(side="left", padx=6)

    def _make_row(self, parent, todo: Todo) -> None:
        row = ctk.CTkFrame(parent, fg_color=("#14142a", "#14142a"), corner_radius=6)
        row.pack(fill="x", pady=3)

        lbl_text = todo.text
        time_str = _fmt_time(todo)
        if time_str:
            lbl_text += f"  [{time_str}]"

        ctk.CTkLabel(row, text=lbl_text, anchor="w",
                     font=ctk.CTkFont(size=12),
                     ).pack(side="left", fill="x", expand=True, padx=10, pady=8)

        ctk.CTkButton(row, text="Unassign", width=78, height=26,
                      font=ctk.CTkFont(size=10),
                      fg_color=("#2a2a3a", "#2a2a3a"),
                      command=lambda t=todo: self._unassign(t),
                      ).pack(side="right", padx=(4, 6), pady=6)

    def _unassign(self, todo: Todo) -> None:
        todo.date = ""
        self._app.save_config_only()
        self._planner._refresh_all()
        self._on_close()
