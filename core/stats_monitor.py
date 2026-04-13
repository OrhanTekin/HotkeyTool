"""
System stats monitor: collects CPU, RAM, disk, and network metrics every 2 s.
Uses psutil (bundled in requirements.txt) — no admin rights needed.
"""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import Callable, Optional


@dataclass
class Stats:
    cpu_pct: float      = 0.0
    ram_pct: float      = 0.0
    ram_used_gb: float  = 0.0
    ram_total_gb: float = 0.0
    disk_pct: float     = 0.0
    disk_used_gb: float = 0.0
    disk_total_gb: float= 0.0
    net_sent_kb: float  = 0.0   # KB/s since last sample
    net_recv_kb: float  = 0.0


class StatsMonitor:
    def __init__(self, on_update: Callable[[Stats], None], interval: float = 2.0) -> None:
        self._on_update = on_update
        self._interval  = interval
        self._stop      = threading.Event()
        self._thread: threading.Thread | None = None
        self._last_net_sent: int = 0
        self._last_net_recv: int = 0

    def start(self) -> None:
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, daemon=True, name="StatsMonitor")
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def _loop(self) -> None:
        try:
            import psutil
        except ImportError:
            return

        # Initialise CPU measurement (first call returns 0.0)
        psutil.cpu_percent(interval=None)
        counters = psutil.net_io_counters()
        self._last_net_sent = counters.bytes_sent
        self._last_net_recv = counters.bytes_recv

        while not self._stop.wait(self._interval):
            try:
                s = self._collect(psutil)
                self._on_update(s)
            except Exception:
                pass

    def _collect(self, psutil) -> Stats:
        cpu  = psutil.cpu_percent(interval=None)
        ram  = psutil.virtual_memory()
        disk = psutil.disk_usage("/")

        counters = psutil.net_io_counters()
        sent_kb = (counters.bytes_sent - self._last_net_sent) / 1024 / self._interval
        recv_kb = (counters.bytes_recv - self._last_net_recv) / 1024 / self._interval
        self._last_net_sent = counters.bytes_sent
        self._last_net_recv = counters.bytes_recv

        return Stats(
            cpu_pct      = cpu,
            ram_pct      = ram.percent,
            ram_used_gb  = ram.used  / 1024**3,
            ram_total_gb = ram.total / 1024**3,
            disk_pct     = disk.percent,
            disk_used_gb = disk.used  / 1024**3,
            disk_total_gb= disk.total / 1024**3,
            net_sent_kb  = max(0.0, sent_kb),
            net_recv_kb  = max(0.0, recv_kb),
        )
