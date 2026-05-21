"""Per-process network connection monitoring."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import List

import psutil

log = logging.getLogger(__name__)


@dataclass
class ProcessNetInfo:
    """A process and its active network connection count."""

    pid: int
    name: str
    connections: int


def get_top_processes(n: int = 5) -> List[ProcessNetInfo]:
    """Return top *n* processes by number of established network connections.

    Returns an empty list if the system denies access (non-admin on Windows)
    or no established connections are found.
    """
    try:
        connections = psutil.net_connections(kind="inet")
    except (psutil.AccessDenied, PermissionError, OSError):
        log.debug("Cannot access network connections (needs admin?)")
        return []

    pid_counts: dict[int, int] = {}
    for conn in connections:
        if conn.pid and conn.pid > 0 and conn.status == "ESTABLISHED":
            pid_counts[conn.pid] = pid_counts.get(conn.pid, 0) + 1

    if not pid_counts:
        return []

    top_pids = sorted(pid_counts.items(), key=lambda x: x[1], reverse=True)[:n]

    result: List[ProcessNetInfo] = []
    for pid, count in top_pids:
        try:
            proc = psutil.Process(pid)
            name = proc.name()
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            name = f"PID {pid}"
        result.append(ProcessNetInfo(pid=pid, name=name, connections=count))
    return result
