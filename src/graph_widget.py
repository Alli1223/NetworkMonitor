"""Live upload/download graph using pyqtgraph.

Holds three rolling buffers (download / upload / latency) and re-renders
them efficiently each tick.  Uses a relative time axis ("seconds ago"),
peak/average horizontal markers, and a secondary Y-axis for latency.
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
LATENCY_COLOR = "#f59e0b"


class RateAxis(pg.AxisItem):
    """Y-axis that formats tick values as KB/s, MB/s, etc."""

    def tickStrings(self, values, scale, spacing):
        return [format_rate(v if v > 0 else 0) for v in values]


class TimeAxis(pg.AxisItem):
    """X-axis that shows '-Ns ago' or '-Nm' for longer durations."""

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


class LatencyAxis(pg.AxisItem):
    """Right Y-axis that formats tick values as milliseconds."""

    def tickStrings(self, values, scale, spacing):
        return [f"{int(round(v))} ms" for v in values]


class TrafficGraph(pg.PlotWidget):
    """Two stacked rolling curves: download (filled) and upload (line),
    plus peak/average markers and a latency overlay on a secondary axis."""

    double_clicked = pyqtSignal()

    def __init__(self, history_seconds: int = 300, parent=None):
        super().__init__(
            parent=parent,
            axisItems={
                "left": RateAxis(orientation="left"),
                "bottom": TimeAxis(orientation="bottom"),
                "right": LatencyAxis(orientation="right"),
            },
        )
        pg.setConfigOptions(antialias=True)
        self.setBackground("#161b22")
        self.showGrid(x=False, y=True, alpha=0.15)

        p = self.getPlotItem()
        p.getAxis("left").setTextPen(QColor("#7d8590"))
        p.getAxis("bottom").setTextPen(QColor("#7d8590"))
        p.getAxis("left").setPen(QColor("#30363d"))
        p.getAxis("bottom").setPen(QColor("#30363d"))
        p.setMenuEnabled(False)
        p.hideButtons()
        self.setMouseEnabled(x=False, y=False)

        self._history = history_seconds
        self._download: Deque[float] = deque([0.0] * history_seconds, maxlen=history_seconds)
        self._upload: Deque[float] = deque([0.0] * history_seconds, maxlen=history_seconds)
        self._latency: Deque[float] = deque([0.0] * history_seconds, maxlen=history_seconds)

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

        # Peak / average horizontal markers
        self._peak_down_line = pg.InfiniteLine(
            angle=0, movable=False,
            pen=pg.mkPen(QColor(79, 157, 255, 80), width=1, style=Qt.PenStyle.DashLine),
        )
        self._avg_down_line = pg.InfiniteLine(
            angle=0, movable=False,
            pen=pg.mkPen(QColor(79, 157, 255, 50), width=1, style=Qt.PenStyle.DotLine),
        )
        self._peak_up_line = pg.InfiniteLine(
            angle=0, movable=False,
            pen=pg.mkPen(QColor(34, 197, 94, 80), width=1, style=Qt.PenStyle.DashLine),
        )
        self._avg_up_line = pg.InfiniteLine(
            angle=0, movable=False,
            pen=pg.mkPen(QColor(34, 197, 94, 50), width=1, style=Qt.PenStyle.DotLine),
        )
        for line in (self._peak_down_line, self._avg_down_line,
                     self._peak_up_line, self._avg_up_line):
            self.addItem(line)

        # Latency overlay — secondary Y-axis on the right
        self._setup_latency_overlay()

        self.setXRange(self._xs[0], 0, padding=0)
        self.setYRange(0, 1024, padding=0.1)  # default 1 KB until we have data
        self.setLimits(xMin=self._xs[0], xMax=0)

    # ------------------------------------------------------------------ #
    #  Latency dual-axis setup                                            #
    # ------------------------------------------------------------------ #

    def _setup_latency_overlay(self) -> None:
        p = self.getPlotItem()
        p.showAxis("right")
        p.getAxis("right").setTextPen(QColor(LATENCY_COLOR))
        p.getAxis("right").setPen(QColor(245, 158, 11, 80))

        self._latency_vb = pg.ViewBox()
        p.scene().addItem(self._latency_vb)
        p.getAxis("right").linkToView(self._latency_vb)
        self._latency_vb.setXLink(p)
        self._latency_vb.setMouseEnabled(x=False, y=False)

        self._latency_curve = pg.PlotCurveItem(
            pen=pg.mkPen(QColor(245, 158, 11, 150), width=1, style=Qt.PenStyle.DashLine),
        )
        self._latency_vb.addItem(self._latency_curve)

        def sync_views():
            self._latency_vb.setGeometry(p.vb.sceneBoundingRect())

        sync_views()
        p.vb.sigResized.connect(sync_views)
        self._sync_latency = sync_views  # prevent garbage-collection

    # ------------------------------------------------------------------ #
    #  Events                                                             #
    # ------------------------------------------------------------------ #

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:
        self.double_clicked.emit()
        super().mouseDoubleClickEvent(event)

    # ------------------------------------------------------------------ #
    #  Theme                                                              #
    # ------------------------------------------------------------------ #

    def apply_theme(self, mode: ModeColors, colors: ColorTheme) -> None:
        self.setBackground(mode.bg_secondary)
        p = self.getPlotItem()
        p.getAxis("left").setTextPen(QColor(mode.text_subtle))
        p.getAxis("bottom").setTextPen(QColor(mode.text_subtle))
        p.getAxis("left").setPen(QColor(mode.border))
        p.getAxis("bottom").setPen(QColor(mode.border))

        # Bandwidth curves
        self._down_curve.setPen(pg.mkPen(QColor(colors.download), width=2))
        self._down_curve.setBrush(
            pg.mkBrush(QColor(colors.fill_r, colors.fill_g, colors.fill_b, colors.fill_a))
        )
        self._up_curve.setPen(pg.mkPen(QColor(colors.upload), width=2))

        # Peak / average markers — derived from theme with reduced alpha
        dl_peak = QColor(colors.download); dl_peak.setAlpha(80)
        dl_avg  = QColor(colors.download); dl_avg.setAlpha(50)
        ul_peak = QColor(colors.upload);   ul_peak.setAlpha(80)
        ul_avg  = QColor(colors.upload);   ul_avg.setAlpha(50)

        self._peak_down_line.setPen(pg.mkPen(dl_peak, width=1, style=Qt.PenStyle.DashLine))
        self._avg_down_line.setPen(pg.mkPen(dl_avg, width=1, style=Qt.PenStyle.DotLine))
        self._peak_up_line.setPen(pg.mkPen(ul_peak, width=1, style=Qt.PenStyle.DashLine))
        self._avg_up_line.setPen(pg.mkPen(ul_avg, width=1, style=Qt.PenStyle.DotLine))

        # Latency axis stays amber regardless of theme
        p.getAxis("right").setTextPen(QColor(LATENCY_COLOR))
        p.getAxis("right").setPen(QColor(245, 158, 11, 80))

    # ------------------------------------------------------------------ #
    #  Data                                                               #
    # ------------------------------------------------------------------ #

    def add_sample(self, download_bps: float, upload_bps: float) -> None:
        self._download.append(max(download_bps, 0.0))
        self._upload.append(max(upload_bps, 0.0))
        self._redraw()

    def add_latency_sample(self, ms: float) -> None:
        self._latency.append(max(ms, 0.0))
        # redrawn on next add_sample tick

    def set_history_seconds(self, seconds: int) -> None:
        seconds = max(10, int(seconds))
        if seconds == self._history:
            return
        self._history = seconds
        for attr in ("_download", "_upload", "_latency"):
            old = list(getattr(self, attr))[-seconds:]
            while len(old) < seconds:
                old.insert(0, 0.0)
            setattr(self, attr, deque(old, maxlen=seconds))
        self._xs = list(range(-(seconds - 1), 1))
        self.setXRange(self._xs[0], 0, padding=0)
        self.setLimits(xMin=self._xs[0], xMax=0)
        self._redraw()

    def reset(self) -> None:
        self._download = deque([0.0] * self._history, maxlen=self._history)
        self._upload = deque([0.0] * self._history, maxlen=self._history)
        self._latency = deque([0.0] * self._history, maxlen=self._history)
        self._redraw()

    # ------------------------------------------------------------------ #
    #  Render                                                             #
    # ------------------------------------------------------------------ #

    def _redraw(self) -> None:
        xs = self._xs
        dl = list(self._download)
        ul = list(self._upload)

        self._down_curve.setData(xs, dl)
        self._up_curve.setData(xs, ul)

        # Auto-scale Y to the visible window, with a sensible floor.
        peak = max(max(dl, default=0.0), max(ul, default=0.0))
        ymax = max(peak * 1.15, 1024.0)  # never below 1 KB/s
        self.setYRange(0, ymax, padding=0)

        # Peak / average markers (rolling, based on visible data)
        if dl:
            self._peak_down_line.setValue(max(dl))
            self._avg_down_line.setValue(sum(dl) / len(dl))
        if ul:
            self._peak_up_line.setValue(max(ul))
            self._avg_up_line.setValue(sum(ul) / len(ul))

        # Latency curve (secondary axis)
        lat = list(self._latency)
        self._latency_curve.setData(xs, lat)
        lat_peak = max(lat, default=1.0)
        self._latency_vb.setYRange(0, max(lat_peak * 1.15, 10.0), padding=0)
