"""
Background scheduler: fires bound actions at configured times.
Checks every 30 seconds; fires a binding at most once per minute per schedule.
"""
from __future__ import annotations

import threading
from datetime import datetime
from typing import TYPE_CHECKING, Callable

if TYPE_CHECKING:
    from core.models import AppConfig, Binding


class SchedulerService:
    def __init__(
        self,
        get_config: Callable[[], "AppConfig"],
        run_binding: Callable[["Binding"], None],
    ) -> None:
        self._get_config = get_config
        self._run_binding = run_binding
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._fired: set[str] = set()   # "schedule_id:YYYY-MM-DD HH:MM"

    def start(self) -> None:
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._loop, daemon=True, name="SchedulerThread"
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()

    # ── internal ─────────────────────────────────────────────────────────────

    def _loop(self) -> None:
        while not self._stop_event.wait(30):
            try:
                self._tick()
            except Exception as exc:
                print(f"[Scheduler] error: {exc}")

    def _tick(self) -> None:
        now = datetime.now()
        weekday  = now.weekday()           # 0 = Monday
        time_str = now.strftime("%H:%M")
        date_str = now.strftime("%Y-%m-%d")
        fire_base = f"{date_str} {time_str}"

        config = self._get_config()
        for schedule in config.schedules:
            if not schedule.enabled:
                continue
            if schedule.time != time_str:
                continue
            if weekday not in schedule.days:
                continue

            fire_key = f"{schedule.id}:{fire_base}"
            if fire_key in self._fired:
                continue  # already fired this minute
            self._fired.add(fire_key)

            # Prune stale entries (keep only today's)
            self._fired = {k for k in self._fired if date_str in k}

            binding = next(
                (b for b in config.bindings if b.id == schedule.binding_id),
                None,
            )
            if binding and binding.enabled and binding.actions:
                threading.Thread(
                    target=self._run_binding,
                    args=(binding,),
                    daemon=True,
                ).start()
