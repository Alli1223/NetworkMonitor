"""Application settings stored via Qt's cross-platform QSettings.

On Windows this lands in the registry; on Linux it lands in ~/.config.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from PyQt6.QtCore import QSettings

from .theme import DEFAULT_COLOR_THEME, DEFAULT_MODE
from .version import APP_ID, ORG_NAME


@dataclass
class AppSettings:
    interface: Optional[str] = None
    history_seconds: int = 300
    update_interval_ms: int = 1000
    start_minimized: bool = False
    minimize_to_tray_on_close: bool = True
    check_updates_on_start: bool = True
    window_opacity: int = 100  # 30..100, percent
    always_on_top: bool = False
    window_geometry: Optional[bytes] = None
    window_state: Optional[bytes] = None
    theme_mode: str = DEFAULT_MODE
    color_theme: str = DEFAULT_COLOR_THEME
    latency_host: str = "8.8.8.8"
    latency_enabled: bool = True
    data_usage_threshold_gb: int = 0  # 0 = disabled
    sidebar_visible: bool = True
    graph_fill: bool = True  # shade the area under the download curve


class SettingsStore:
    """Thin wrapper around QSettings, typed for our app."""

    def __init__(self) -> None:
        self._q = QSettings(ORG_NAME, APP_ID)

    def load(self) -> AppSettings:
        s = AppSettings()
        s.interface = self._q.value("interface", None, type=str) or None
        s.history_seconds = int(self._q.value("history_seconds", s.history_seconds, type=int))
        # One-time migration: old default was 60s, new default is 300s (v0.2.1)
        if not self._to_bool(self._q.value("_migrated_history_300", False)):
            if s.history_seconds == 60:
                s.history_seconds = 300
            self._q.setValue("_migrated_history_300", True)
        s.update_interval_ms = int(self._q.value("update_interval_ms", s.update_interval_ms, type=int))
        s.start_minimized = self._to_bool(self._q.value("start_minimized", s.start_minimized))
        s.minimize_to_tray_on_close = self._to_bool(
            self._q.value("minimize_to_tray_on_close", s.minimize_to_tray_on_close)
        )
        s.check_updates_on_start = self._to_bool(
            self._q.value("check_updates_on_start", s.check_updates_on_start)
        )
        s.window_opacity = int(self._q.value("window_opacity", s.window_opacity, type=int))
        s.always_on_top = self._to_bool(self._q.value("always_on_top", s.always_on_top))
        geom = self._q.value("window_geometry", None)
        s.window_geometry = bytes(geom) if geom else None
        state = self._q.value("window_state", None)
        s.window_state = bytes(state) if state else None
        s.theme_mode = self._q.value("theme_mode", s.theme_mode, type=str)
        s.color_theme = self._q.value("color_theme", s.color_theme, type=str)
        s.latency_host = self._q.value("latency_host", s.latency_host, type=str)
        s.latency_enabled = self._to_bool(self._q.value("latency_enabled", s.latency_enabled))
        s.data_usage_threshold_gb = int(
            self._q.value("data_usage_threshold_gb", s.data_usage_threshold_gb, type=int)
        )
        s.sidebar_visible = self._to_bool(self._q.value("sidebar_visible", s.sidebar_visible))
        s.graph_fill = self._to_bool(self._q.value("graph_fill", s.graph_fill))
        return s

    def save(self, s: AppSettings) -> None:
        self._q.setValue("interface", s.interface or "")
        self._q.setValue("history_seconds", int(s.history_seconds))
        self._q.setValue("update_interval_ms", int(s.update_interval_ms))
        self._q.setValue("start_minimized", bool(s.start_minimized))
        self._q.setValue("minimize_to_tray_on_close", bool(s.minimize_to_tray_on_close))
        self._q.setValue("check_updates_on_start", bool(s.check_updates_on_start))
        self._q.setValue("window_opacity", int(s.window_opacity))
        self._q.setValue("always_on_top", bool(s.always_on_top))
        if s.window_geometry is not None:
            self._q.setValue("window_geometry", s.window_geometry)
        if s.window_state is not None:
            self._q.setValue("window_state", s.window_state)
        self._q.setValue("theme_mode", s.theme_mode)
        self._q.setValue("color_theme", s.color_theme)
        self._q.setValue("latency_host", s.latency_host)
        self._q.setValue("latency_enabled", bool(s.latency_enabled))
        self._q.setValue("data_usage_threshold_gb", int(s.data_usage_threshold_gb))
        self._q.setValue("sidebar_visible", bool(s.sidebar_visible))
        self._q.setValue("graph_fill", bool(s.graph_fill))
        self._q.sync()

    @staticmethod
    def _to_bool(value) -> bool:
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.lower() in ("1", "true", "yes", "on")
        if value is None:
            return False
        return bool(value)
