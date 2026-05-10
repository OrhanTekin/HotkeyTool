"""
Pure stats helpers for the planner — overdue count, this-week count, today
progress, and a daily streak counter. UI-free so they're trivially testable.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Iterable, Optional, Tuple

from core.models import Todo


def _parse(date_str: str) -> Optional[date]:
    if not date_str:
        return None
    try:
        return datetime.strptime(date_str, "%Y-%m-%d").date()
    except Exception:
        return None


def overdue_count(todos: Iterable[Todo], today: Optional[date] = None) -> int:
    today = today or date.today()
    n = 0
    for t in todos:
        if t.completed:
            continue
        d = _parse(t.date)
        if d is not None and d < today:
            n += 1
    return n


def this_week_count(todos: Iterable[Todo], today: Optional[date] = None) -> int:
    """Open tasks dated within the next 7 days (today included)."""
    today = today or date.today()
    end = today + timedelta(days=7)
    n = 0
    for t in todos:
        if t.completed:
            continue
        d = _parse(t.date)
        if d is not None and today <= d < end:
            n += 1
    return n


def today_progress(todos: Iterable[Todo], today: Optional[date] = None) -> Tuple[int, int]:
    """Returns (done, total) for tasks dated today."""
    today = today or date.today()
    done = total = 0
    for t in todos:
        d = _parse(t.date)
        if d != today:
            continue
        total += 1
        if t.completed:
            done += 1
    return done, total


def daily_streak(todos: Iterable[Todo], today: Optional[date] = None,
                 max_lookback: int = 365) -> int:
    """Count consecutive days walking back from yesterday where every dated
    task for that day is completed. Days with zero dated tasks don't count
    toward (or break) the streak — they're skipped. Today itself is excluded
    so the streak doesn't reset every morning while the user is still working."""
    today = today or date.today()
    todos = list(todos)
    streak = 0
    cur = today - timedelta(days=1)
    for _ in range(max_lookback):
        day_tasks = [t for t in todos if _parse(t.date) == cur]
        if day_tasks:
            if all(t.completed for t in day_tasks):
                streak += 1
            else:
                break
        cur = cur - timedelta(days=1)
    return streak
