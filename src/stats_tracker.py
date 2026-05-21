"""Session statistics and persistent data usage tracking."""

from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import dataclass, field
from datetime import date, timedelta

log = logging.getLogger(__name__)


def format_duration(seconds: float) -> str:
    """Human-friendly duration: '45s', '3m 12s', '2h 05m'."""
    s = int(seconds)
    if s < 60:
        return f"{s}s"
    m, s = divmod(s, 60)
    if m < 60:
        return f"{m}m {s:02d}s"
    h, m = divmod(m, 60)
    return f"{h}h {m:02d}m"


@dataclass
class SessionStats:
    """In-memory statistics for the current app session."""

    start_time: float = field(default_factory=time.time)
    total_downloaded: float = 0.0
    total_uploaded: float = 0.0
    peak_download_bps: float = 0.0
    peak_upload_bps: float = 0.0

    def update(self, download_bps: float, upload_bps: float, interval_s: float) -> None:
        self.total_downloaded += download_bps * interval_s
        self.total_uploaded += upload_bps * interval_s
        self.peak_download_bps = max(self.peak_download_bps, download_bps)
        self.peak_upload_bps = max(self.peak_upload_bps, upload_bps)

    @property
    def duration_seconds(self) -> float:
        return time.time() - self.start_time

    def reset(self) -> None:
        self.start_time = time.time()
        self.total_downloaded = 0.0
        self.total_uploaded = 0.0
        self.peak_download_bps = 0.0
        self.peak_upload_bps = 0.0


class DataUsageStore:
    """Persists daily bandwidth totals to a JSON file."""

    def __init__(self, data_dir: str) -> None:
        self._path = os.path.join(data_dir, "data_usage.json")
        self._data: dict = self._load()
        self._dirty = False

    def _load(self) -> dict:
        try:
            with open(self._path, "r") as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            return {"daily": {}}

    def save(self) -> None:
        if not self._dirty:
            return
        try:
            os.makedirs(os.path.dirname(self._path), exist_ok=True)
            with open(self._path, "w") as f:
                json.dump(self._data, f, indent=2)
            self._dirty = False
        except OSError:
            log.exception("Failed to save data usage")

    def add_bytes(self, downloaded: float, uploaded: float) -> None:
        today = date.today().isoformat()
        if today not in self._data["daily"]:
            self._data["daily"][today] = {"down": 0.0, "up": 0.0}
        self._data["daily"][today]["down"] += downloaded
        self._data["daily"][today]["up"] += uploaded
        self._dirty = True

    def get_today(self) -> tuple[float, float]:
        today = date.today().isoformat()
        entry = self._data["daily"].get(today, {"down": 0.0, "up": 0.0})
        return entry["down"], entry["up"]

    def get_this_week(self) -> tuple[float, float]:
        today = date.today()
        week_start = today - timedelta(days=today.weekday())
        down = up = 0.0
        for i in range(7):
            d = (week_start + timedelta(days=i)).isoformat()
            if d in self._data["daily"]:
                down += self._data["daily"][d]["down"]
                up += self._data["daily"][d]["up"]
        return down, up

    def get_this_month(self) -> tuple[float, float]:
        prefix = date.today().strftime("%Y-%m-")
        down = up = 0.0
        for d, entry in self._data["daily"].items():
            if d.startswith(prefix):
                down += entry["down"]
                up += entry["up"]
        return down, up

    def prune_old(self, keep_days: int = 90) -> None:
        cutoff = (date.today() - timedelta(days=keep_days)).isoformat()
        self._data["daily"] = {
            d: v for d, v in self._data["daily"].items() if d >= cutoff
        }
        self._dirty = True
