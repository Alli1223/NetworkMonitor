"""Full-size rolling detail graph for a single system metric.

Used in the main area when the user clicks a tile in the left rail.  Shows one
primary rolling curve — a percentage (CPU/RAM/GPU) or a throughput (disk) — and
an optional temperature curve on a secondary right-hand axis (CPU/GPU).

Mirrors the look of :class:`~src.graph_widget.TrafficGraph`: dark background,
horizontal grid, relative "seconds ago" time axis, thin 1px line with a light
filled area.
"""

from __future__ import annotations

from collections import deque
from typing import Deque, List, Optional

import pyqtgraph as pg
from PyQt6.QtCore import pyqtSignal
from PyQt6.QtGui import QColor, QMouseEvent

from .graph_widget import AxisAutoScaler, RateAxis, TimeAxis
from .theme import ColorTheme, ModeColors

LATENCY_COLOR = "#f59e0b"
TEMP_COLOR = "#f97316"


class PercentAxis(pg.AxisItem):
    """Left Y-axis formatting tick values as percentages."""

    def tickStrings(self, values, scale, spacing):
        return [f"{int(round(v))}%" for v in values]


class TempAxis(pg.AxisItem):
    """Right Y-axis formatting tick values as degrees Celsius."""

    def tickStrings(self, values, scale, spacing):
        return [f"{int(round(v))}°" for v in values]


class MetricGraph(pg.PlotWidget):
    """A single-metric rolling graph (percentage or throughput)."""

    double_clicked = pyqtSignal()

    def __init__(
        self,
        history_seconds: int = 300,
        mode: str = "percent",          # "percent" | "rate"
        accent: str = "#4f9dff",
        with_temp: bool = False,
        parent=None,
    ):
        left_axis = PercentAxis(orientation="left") if mode == "percent" \
            else RateAxis(orientation="left")
        super().__init__(
            parent=parent,
            axisItems={"left": left_axis, "bottom": TimeAxis(orientation="bottom")},
        )
        pg.setConfigOptions(antialias=True)
        self._mode = mode
        self._accent = accent
        self._with_temp = with_temp
        self._history = history_seconds

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

        self._data: Deque[float] = deque([0.0] * history_seconds, maxlen=history_seconds)
        self._temp: Deque[float] = deque([0.0] * history_seconds, maxlen=history_seconds)
        self._xs: List[int] = list(range(-(history_seconds - 1), 1))

        self._curve = self.plot(
            self._xs, list(self._data),
            pen=pg.mkPen(QColor(accent), width=1),
            fillLevel=0,
            brush=pg.mkBrush(self._accent_fill(accent)),
        )

        self._temp_vb = None
        self._temp_curve = None
        if with_temp:
            self._setup_temp_overlay()

        # Throughput has no natural ceiling, so its axis follows the peak
        # currently on screen; percentages stay pinned to 0-100.
        self._rate_scaler = None
        self._temp_scaler = None
        if mode != "percent":
            self._rate_scaler = AxisAutoScaler(
                lambda ymax: self.setYRange(0, ymax, padding=0),
                minimum=1024.0, parent=self,
            )
        if self._temp_vb is not None:
            self._temp_scaler = AxisAutoScaler(
                lambda ymax: self._temp_vb.setYRange(0, ymax, padding=0),
                minimum=10.0, parent=self,
            )

        self.setXRange(self._xs[0], 0, padding=0)
        self.setLimits(xMin=self._xs[0], xMax=0)
        if mode == "percent":
            self.setYRange(0, 100, padding=0)

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:
        self.double_clicked.emit()
        super().mouseDoubleClickEvent(event)

    # ------------------------------------------------------------------ #
    #  Temperature overlay                                                #
    # ------------------------------------------------------------------ #

    def _setup_temp_overlay(self) -> None:
        p = self.getPlotItem()
        p.showAxis("right")
        p.setAxisItems({"right": TempAxis(orientation="right")})
        p.getAxis("right").setTextPen(QColor(TEMP_COLOR))
        p.getAxis("right").setPen(QColor(249, 115, 22, 90))

        self._temp_vb = pg.ViewBox()
        p.scene().addItem(self._temp_vb)
        p.getAxis("right").linkToView(self._temp_vb)
        self._temp_vb.setXLink(p)
        self._temp_vb.setMouseEnabled(x=False, y=False)

        self._temp_curve = pg.PlotCurveItem(
            pen=pg.mkPen(QColor(TEMP_COLOR), width=1)
        )
        self._temp_vb.addItem(self._temp_curve)

        def sync():
            self._temp_vb.setGeometry(p.vb.sceneBoundingRect())

        sync()
        p.vb.sigResized.connect(sync)
        self._sync_temp = sync  # keep ref alive

    @staticmethod
    def _accent_fill(accent: str) -> QColor:
        c = QColor(accent)
        c.setAlpha(45)
        return c

    # ------------------------------------------------------------------ #
    #  Data                                                               #
    # ------------------------------------------------------------------ #

    def push(self, value: float, temp: Optional[float] = None) -> None:
        self._data.append(max(0.0, float(value)))
        if temp is not None:
            self._temp.append(max(0.0, float(temp)))
        else:
            self._temp.append(self._temp[-1] if self._temp else 0.0)
        self._redraw()

    def set_history_seconds(self, seconds: int) -> None:
        seconds = max(10, int(seconds))
        if seconds == self._history:
            return
        self._history = seconds
        for attr in ("_data", "_temp"):
            old = list(getattr(self, attr))[-seconds:]
            while len(old) < seconds:
                old.insert(0, 0.0)
            setattr(self, attr, deque(old, maxlen=seconds))
        self._xs = list(range(-(seconds - 1), 1))
        self.setXRange(self._xs[0], 0, padding=0)
        self.setLimits(xMin=self._xs[0], xMax=0)
        # The window changed wholesale, so jump to the new scale.
        self._redraw(snap_scale=True)

    def reset(self) -> None:
        self._data = deque([0.0] * self._history, maxlen=self._history)
        self._temp = deque([0.0] * self._history, maxlen=self._history)
        self._redraw(snap_scale=True)

    def _redraw(self, snap_scale: bool = False) -> None:
        xs = self._xs
        data = list(self._data)
        self._curve.setData(xs, data)

        if self._rate_scaler is not None:
            self._rate_scaler.set_target(max(data, default=0.0), snap=snap_scale)

        if self._with_temp and self._temp_curve is not None:
            temp = list(self._temp)
            self._temp_curve.setData(xs, temp)
            self._temp_scaler.set_target(max(temp, default=0.0), snap=snap_scale)

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
