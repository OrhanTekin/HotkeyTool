from __future__ import annotations
import copy
import uuid
from dataclasses import dataclass, field
from typing import List


@dataclass
class Action:
    type: str
    value: str
    args: str = ""
    delay_after_ms: int = 0

    def to_dict(self) -> dict:
        return {"type": self.type, "value": self.value,
                "args": self.args, "delay_after_ms": self.delay_after_ms}

    @classmethod
    def from_dict(cls, d: dict) -> "Action":
        return cls(type=d.get("type", "open_url"), value=d.get("value", ""),
                   args=d.get("args", ""), delay_after_ms=d.get("delay_after_ms", 0))


@dataclass
class Binding:
    id: str
    hotkey: str
    name: str
    enabled: bool = True
    actions: List[Action] = field(default_factory=list)

    @classmethod
    def new(cls) -> "Binding":
        return cls(id=str(uuid.uuid4()), hotkey="", name="")

    def to_dict(self) -> dict:
        return {"id": self.id, "hotkey": self.hotkey, "name": self.name,
                "enabled": self.enabled, "actions": [a.to_dict() for a in self.actions]}

    @classmethod
    def from_dict(cls, d: dict) -> "Binding":
        return cls(id=d.get("id", str(uuid.uuid4())), hotkey=d.get("hotkey", ""),
                   name=d.get("name", "Binding"), enabled=d.get("enabled", True),
                   actions=[Action.from_dict(a) for a in d.get("actions", [])])

    def duplicate(self) -> "Binding":
        b = copy.deepcopy(self)
        b.id = str(uuid.uuid4())
        b.name = f"{self.name} (copy)"
        return b


@dataclass
class Schedule:
    id: str
    binding_id: str
    name: str
    enabled: bool = True
    time: str = "09:00"
    days: List[int] = field(default_factory=lambda: list(range(7)))

    @classmethod
    def new(cls) -> "Schedule":
        return cls(id=str(uuid.uuid4()), binding_id="", name="")

    def to_dict(self) -> dict:
        return {"id": self.id, "binding_id": self.binding_id, "name": self.name,
                "enabled": self.enabled, "time": self.time, "days": self.days}

    @classmethod
    def from_dict(cls, d: dict) -> "Schedule":
        return cls(id=d.get("id", str(uuid.uuid4())), binding_id=d.get("binding_id", ""),
                   name=d.get("name", "Schedule"), enabled=d.get("enabled", True),
                   time=d.get("time", "09:00"), days=d.get("days", list(range(7))))


@dataclass
class Snippet:
    id: str
    abbreviation: str    # e.g. "@@addr"
    expansion: str       # e.g. "123 Main St, City"
    enabled: bool = True

    @classmethod
    def new(cls) -> "Snippet":
        return cls(id=str(uuid.uuid4()), abbreviation="", expansion="")

    def to_dict(self) -> dict:
        return {"id": self.id, "abbreviation": self.abbreviation,
                "expansion": self.expansion, "enabled": self.enabled}

    @classmethod
    def from_dict(cls, d: dict) -> "Snippet":
        return cls(id=d.get("id", str(uuid.uuid4())),
                   abbreviation=d.get("abbreviation", ""),
                   expansion=d.get("expansion", ""),
                   enabled=d.get("enabled", True))


@dataclass
class Note:
    id: str
    name: str
    content: str = ""

    @classmethod
    def new(cls, name: str = "Note") -> "Note":
        return cls(id=str(uuid.uuid4()), name=name, content="")

    def to_dict(self) -> dict:
        return {"id": self.id, "name": self.name, "content": self.content}

    @classmethod
    def from_dict(cls, d: dict) -> "Note":
        return cls(id=d.get("id", str(uuid.uuid4())),
                   name=d.get("name", "Note"), content=d.get("content", ""))


@dataclass
class WindowState:
    title: str
    exe: str
    x: int
    y: int
    width: int
    height: int
    maximized: bool = False

    def to_dict(self) -> dict:
        return {"title": self.title, "exe": self.exe,
                "x": self.x, "y": self.y, "width": self.width, "height": self.height,
                "maximized": self.maximized}

    @classmethod
    def from_dict(cls, d: dict) -> "WindowState":
        return cls(title=d.get("title", ""), exe=d.get("exe", ""),
                   x=d.get("x", 0), y=d.get("y", 0),
                   width=d.get("width", 800), height=d.get("height", 600),
                   maximized=d.get("maximized", False))


@dataclass
class WindowLayout:
    id: str
    name: str
    windows: List[WindowState] = field(default_factory=list)

    @classmethod
    def new(cls, name: str = "Layout") -> "WindowLayout":
        return cls(id=str(uuid.uuid4()), name=name)

    def to_dict(self) -> dict:
        return {"id": self.id, "name": self.name,
                "windows": [w.to_dict() for w in self.windows]}

    @classmethod
    def from_dict(cls, d: dict) -> "WindowLayout":
        return cls(id=d.get("id", str(uuid.uuid4())), name=d.get("name", "Layout"),
                   windows=[WindowState.from_dict(w) for w in d.get("windows", [])])


@dataclass
class Todo:
    id: str
    text: str
    time_type: str = "none"        # "none" | "duration" | "timespan"
    duration_mins: int = 0         # total minutes (days*1440 + h*60 + m)
    start_time: str = ""           # "HH:MM"
    end_time: str = ""             # "HH:MM"
    date: str = ""                 # "YYYY-MM-DD" or ""
    color: str = "#1e3a5f"
    completed: bool = False
    priority: str = "medium"       # "low" | "medium" | "high"
    category: str = ""             # free tag, matches planner_categories
    recurrence: str = "none"       # "none" | "daily" | "weekly" | "monthly" | "yearly"
    recurrence_days: List[int] = field(default_factory=list)  # 0=Mon…6=Sun for weekly
    subtasks: List[dict] = field(default_factory=list)        # [{"id","text","completed"}]

    @classmethod
    def new(cls, text: str = "") -> "Todo":
        return cls(id=str(uuid.uuid4()), text=text)

    def to_dict(self) -> dict:
        return {"id": self.id, "text": self.text, "time_type": self.time_type,
                "duration_mins": self.duration_mins,
                "start_time": self.start_time, "end_time": self.end_time,
                "date": self.date, "color": self.color, "completed": self.completed,
                "priority": self.priority, "category": self.category,
                "recurrence": self.recurrence, "recurrence_days": self.recurrence_days,
                "subtasks": self.subtasks}

    @classmethod
    def from_dict(cls, d: dict) -> "Todo":
        return cls(id=d.get("id", str(uuid.uuid4())),
                   text=d.get("text", ""),
                   time_type=d.get("time_type", "none"),
                   duration_mins=d.get("duration_mins", 0),
                   start_time=d.get("start_time", ""),
                   end_time=d.get("end_time", ""),
                   date=d.get("date", ""),
                   color=d.get("color", "#1e3a5f"),
                   completed=d.get("completed", False),
                   priority=d.get("priority", "medium"),
                   category=d.get("category", ""),
                   recurrence=d.get("recurrence", "none"),
                   recurrence_days=d.get("recurrence_days", []),
                   subtasks=d.get("subtasks", []))


@dataclass
class AppSettings:
    autostart: bool = False
    minimize_to_tray_on_close: bool = True
    theme: str = "dark"
    stats_widget_on_startup: bool = False
    notes_geometry: str = ""

    def to_dict(self) -> dict:
        return {"autostart": self.autostart,
                "minimize_to_tray_on_close": self.minimize_to_tray_on_close,
                "theme": self.theme,
                "stats_widget_on_startup": self.stats_widget_on_startup,
                "notes_geometry": self.notes_geometry}

    @classmethod
    def from_dict(cls, d: dict) -> "AppSettings":
        return cls(autostart=d.get("autostart", False),
                   minimize_to_tray_on_close=d.get("minimize_to_tray_on_close", True),
                   theme=d.get("theme", "dark"),
                   stats_widget_on_startup=d.get("stats_widget_on_startup", False),
                   notes_geometry=d.get("notes_geometry", ""))


@dataclass
class AppConfig:
    version: int = 2
    listening: bool = True
    settings: AppSettings = field(default_factory=AppSettings)
    bindings: List[Binding] = field(default_factory=list)
    schedules: List[Schedule] = field(default_factory=list)
    snippets: List[Snippet] = field(default_factory=list)
    layouts: List[WindowLayout] = field(default_factory=list)
    notes: List[Note] = field(default_factory=lambda: [Note.new("Quick Note")])
    clipboard_history: List[str] = field(default_factory=list)
    todos: List[Todo] = field(default_factory=list)
    planner_categories: List[str] = field(
        default_factory=lambda: ["Work", "Personal", "Health", "Finance"])

    def to_dict(self) -> dict:
        return {"version": self.version, "listening": self.listening,
                "settings": self.settings.to_dict(),
                "bindings": [b.to_dict() for b in self.bindings],
                "schedules": [s.to_dict() for s in self.schedules],
                "snippets":  [s.to_dict() for s in self.snippets],
                "layouts":   [l.to_dict() for l in self.layouts],
                "notes":     [n.to_dict() for n in self.notes],
                "clipboard_history": self.clipboard_history[:10],
                "todos":     [t.to_dict() for t in self.todos],
                "planner_categories": self.planner_categories}

    @classmethod
    def from_dict(cls, d: dict) -> "AppConfig":
        notes_raw = d.get("notes", [])
        notes = [Note.from_dict(n) for n in notes_raw] if notes_raw else [Note.new("Quick Note")]
        return cls(version=d.get("version", 2), listening=d.get("listening", True),
                   settings=AppSettings.from_dict(d.get("settings", {})),
                   bindings=[Binding.from_dict(b) for b in d.get("bindings", [])],
                   schedules=[Schedule.from_dict(s) for s in d.get("schedules", [])],
                   snippets=[Snippet.from_dict(s) for s in d.get("snippets", [])],
                   layouts=[WindowLayout.from_dict(l) for l in d.get("layouts", [])],
                   notes=notes,
                   clipboard_history=d.get("clipboard_history", []),
                   todos=[Todo.from_dict(t) for t in d.get("todos", [])],
                   planner_categories=d.get(
                       "planner_categories", ["Work", "Personal", "Health", "Finance"]))
