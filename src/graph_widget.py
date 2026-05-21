"""Live upload/download graph using pyqtgraph.

Holds two rolling buffers (download / upload, in bytes/sec) and re-renders
them efficiently each tick. Uses a relative time axis ("seconds ago").
"""

from __future__ import annotations

from collections import deque
from typing import Deque

import pyqtgraph as pg
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QColor, QMouseEvent

from .network_monitor import format_rate
from .theme import ColorTheme, ModeColors


DOWNLOAD_COLOR = "#4f9dff"
UPLOAD_COLOR = "#22c55e"


class RateAxis(pg.AxisItem):
    """Y-axis that formats tick values as KB/s, MB/s, etc."""

    def tickStrings(self, values, scale, spacing):
        return [format_rate(v if v > 0 else 0) for v in values]


class TimeAxis(pg.AxisItem):
    """X-axis that shows 'Ns ago' for negative time values."""

    def tickStrings(self, values, scale, spacing):
        out = []
        for v in values:
            secs = int(round(-v))
            if secs == 0:
                out.append("now")
            elif secs >= 60:
                m, s = divmod(secs, 60)
                out.append(f"-{m}m{s:02d}s" if s else f"-{m}m")
            else:
                out.append(f"-{secs}s")
        return out


class TrafficGraph(pg.PlotWidget):
    """Two stacked rolling curves: download (filled) and upload (line)."""

    double_clicked = pyqtSignal()

    def __init__(self, history_seconds: int = 60, parent=None):
        super().__init__(
            parent=parent,
            axisItems={"left": RateAxis(orientation="left"), "bottom": TimeAxis(orientation="bottom")},
        )
        pg.setConfigOptions(antialias=True)
        self.setBackground("#161b22")
        self.showGrid(x=False, y=True, alpha=0.15)
        self.getPlotItem().getAxis("left").setTextPen(QColor("#7d8590"))
        self.getPlotItem().getAxis("bottom").setTextPen(QColor("#7d8590"))
        self.getPlotItem().getAxis("left").setPen(QColor("#30363d"))
        self.getPlotItem().getAxis("bottom").setPen(QColor("#30363d"))
        self.getPlotItem().setMenuEnabled(False)
        self.getPlotItem().hideButtons()
        self.setMouseEnabled(x=False, y=False)

        self._history = history_seconds
        self._download: Deque[float] = deque([0.0] * history_seconds, maxlen=history_seconds)
        self._upload: Deque[float] = deque([0.0] * history_seconds, maxlen=history_seconds)

        # Time axis goes from -(history-1) ... 0
        self._xs = list(range(-(history_seconds - 1), 1))

        # Download: filled area
        self._down_curve = self.plot(
            self._xs, list(self._download),
            pen=pg.mkPen(QColor(DOWNLOAD_COLOR), width=2),
            fillLevel=0,
            brush=pg.mkBrush(QColor(79, 157, 255, 60)),
        )
        # Upload: line
        self._up_curve = self.plot(
            self._xs, list(self._upload),
            pen=pg.mkPen(QColor(UPLOAD_COLOR), width=2),
        )

        self.setXRange(self._xs[0], 0, padding=0)
        self.setYRange(0, 1024, padding=0.1)  # default 1KB until we have data
        self.setLimits(xMin=self._xs[0], xMax=0)

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:
        self.double_clicked.emit()
        super().mouseDoubleClickEvent(event)

    def apply_theme(self, mode: ModeColors, colors: ColorTheme) -> None:
        self.setBackground(mode.bg_secondary)
        self.getPlotItem().getAxis("left").setTextPen(QColor(mode.text_subtle))
        self.getPlotItem().getAxis("bottom").setTextPen(QColor(mode.text_subtle))
        self.getPlotItem().getAxis("left").setPen(QColor(mode.border))
        self.getPlotItem().getAxis("bottom").setPen(QColor(mode.border))
        self._down_curve.setPen(pg.mkPen(QColor(colors.download), width=2))
        self._down_curve.setBrush(
            pg.mkBrush(QColor(colors.fill_r, colors.fill_g, colors.fill_b, colors.fill_a))
        )
        self._up_curve.setPen(pg.mkPen(QColor(colors.upload), width=2))

    def set_history_seconds(self, seconds: int) -> None:
        seconds = max(10, int(seconds))
        if seconds == self._history:
            return
        self._history = seconds
        # Re-pad buffers to new size, preserving the most recent samples
        d = list(self._download)[-seconds:]
        u = list(self._upload)[-seconds:]
        while len(d) < seconds:
            d.insert(0, 0.0)
        while len(u) < seconds:
            u.insert(0, 0.0)
        self._download = deque(d, maxlen=seconds)
        self._upload = deque(u, maxlen=seconds)
        self._xs = list(range(-(seconds - 1), 1))
        self.setXRange(self._xs[0], 0, padding=0)
        self.setLimits(xMin=self._xs[0], xMax=0)
        self._redraw()

    def add_sample(self, download_bps: float, upload_bps: float) -> None:
        self._download.append(max(download_bps, 0.0))
        self._upload.append(max(upload_bps, 0.0))
        self._redraw()

    def reset(self) -> None:
        self._download = deque([0.0] * self._history, maxlen=self._history)
        self._upload = deque([0.0] * self._history, maxlen=self._history)
        self._redraw()

    def _redraw(self) -> None:
        self._down_curve.setData(self._xs, list(self._download))
        self._up_curve.setData(self._xs, list(self._upload))
        # Auto-scale Y to the visible window, with a sensible floor.
        peak = max(max(self._download, default=0.0), max(self._upload, default=0.0))
        ymax = max(peak * 1.15, 1024.0)  # never below 1 KB/s so axis isn't jittery
        self.setYRange(0, ymax, padding=0)
