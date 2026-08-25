"""Live upload/download graph using pyqtgraph.

Holds three rolling buffers (download / upload / latency) and re-renders
them efficiently each tick.  Uses a relative time axis ("seconds ago"),
peak/average horizontal markers, and a secondary Y-axis for latency.
"""

from __future__ import annotations

from collections import deque
from typing import Deque

import pyqtgraph as pg
from PyQt6.QtCore import QObject, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QMouseEvent

from .network_monitor import format_rate
from .theme import ColorTheme, ModeColors


DOWNLOAD_COLOR = "#4f9dff"
UPLOAD_COLOR = "#22c55e"
LATENCY_COLOR = "#f59e0b"

# Which series the network graph draws.
VIEW_BOTH = "both"
VIEW_BANDWIDTH = "bandwidth"   # download / upload only
VIEW_PING = "ping"             # latency only
VIEW_MODES = (VIEW_BOTH, VIEW_BANDWIDTH, VIEW_PING)


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


class AxisAutoScaler(QObject):
    """Eases a plot's Y-range so whatever is on screen fills the height.

    :meth:`set_target` is fed the highest value currently drawn on every
    redraw; a ~30 fps timer then glides the applied ceiling toward it instead
    of snapping.  Growing is quick so spikes are never clipped for long,
    shrinking is slower so the chart settles gently once traffic dies down.
    """

    #: Ignore target changes smaller than this so axis labels don't twitch.
    DEADBAND = 0.01

    def __init__(self, apply_range, minimum: float, headroom: float = 1.02,
                 grow: float = 0.25, shrink: float = 0.13, parent=None):
        super().__init__(parent)
        self._apply = apply_range
        self._minimum = float(minimum)
        self._headroom = headroom
        self._grow = grow
        self._shrink = shrink
        self._current = float(minimum)
        self._target = float(minimum)

        self._timer = QTimer(self)
        self._timer.setInterval(33)
        self._timer.timeout.connect(self._step)
        self._apply(self._current)

    def set_target(self, peak: float, snap: bool = False) -> None:
        """Aim the axis at *peak* (plus a little headroom).

        Pass ``snap=True`` to jump there immediately — used when the data is
        replaced wholesale rather than scrolled by one sample.
        """
        target = max(float(peak) * self._headroom, self._minimum)
        if snap:
            self._timer.stop()
            self._target = self._current = target
            self._apply(target)
            return
        if abs(target - self._target) <= self._target * self.DEADBAND:
            return
        self._target = target
        if not self._timer.isActive():
            self._timer.start()

    def _step(self) -> None:
        gap = self._target - self._current
        if abs(gap) <= self._target * 0.005:
            self._current = self._target
            self._timer.stop()
        elif gap > 0:
            self._current += gap * self._grow
        else:
            # Shrinking is geometric so that dropping from 10 MB/s to a few
            # KB/s glides at the same rate as merely halving does; a linear
            # ease would crawl for several seconds after a big spike.
            self._current *= (self._target / self._current) ** self._shrink
        self._apply(self._current)


def _ema_smooth(data: list[float], alpha: float = 0.3) -> list[float]:
    """Apply Exponential Moving Average smoothing.

    *alpha* controls responsiveness: 0.0 = fully smoothed (flat), 1.0 = no
    smoothing.  A value around 0.25-0.35 is a good balance for 1-second
    network traffic samples.
    """
    if not data:
        return data
    out = [data[0]]
    for i in range(1, len(data)):
        out.append(alpha * data[i] + (1.0 - alpha) * out[-1])
    return out


class TrafficGraph(pg.PlotWidget):
    """Two stacked rolling curves: download (optionally filled) and upload
    (line), plus peak/average markers and a latency overlay on a secondary
    axis.

    Raw samples are kept in rolling deques; an EMA-smoothed version is
    computed on each redraw for visually cleaner curves.
    """

    double_clicked = pyqtSignal()

    def __init__(self, history_seconds: int = 300, smooth_alpha: float = 0.3,
                 fill_enabled: bool = True, view_mode: str = VIEW_BOTH, parent=None):
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
        self._smooth_alpha = smooth_alpha
        self._fill_enabled = fill_enabled
        self._view_mode = view_mode if view_mode in VIEW_MODES else VIEW_BOTH
        self._download: Deque[float] = deque([0.0] * history_seconds, maxlen=history_seconds)
        self._upload: Deque[float] = deque([0.0] * history_seconds, maxlen=history_seconds)
        self._latency: Deque[float] = deque([0.0] * history_seconds, maxlen=history_seconds)

        # Time axis goes from -(history-1) ... 0
        self._xs = list(range(-(history_seconds - 1), 1))

        # Download: line with optional filled area underneath
        self._down_curve = self.plot(
            self._xs, list(self._download),
            pen=pg.mkPen(QColor(DOWNLOAD_COLOR), width=1),
            fillLevel=0 if fill_enabled else None,
            brush=pg.mkBrush(QColor(79, 157, 255, 60)),
        )
        # Upload: line
        self._up_curve = self.plot(
            self._xs, list(self._upload),
            pen=pg.mkPen(QColor(UPLOAD_COLOR), width=1),
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
        self._apply_view_mode()

        # Both Y-axes track the peak that is currently on screen, gliding
        # up and down as traffic changes (default 1 KB/s / 10 ms until we
        # have data).
        self._rate_scaler = AxisAutoScaler(
            lambda ymax: self.setYRange(0, ymax, padding=0),
            minimum=1024.0, parent=self,
        )
        self._latency_scaler = AxisAutoScaler(
            lambda ymax: self._latency_vb.setYRange(0, ymax, padding=0),
            minimum=10.0, parent=self,
        )

        self.setXRange(self._xs[0], 0, padding=0)
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
    #  View mode (bandwidth / ping / both)                                #
    # ------------------------------------------------------------------ #

    def set_view_mode(self, mode: str) -> None:
        """Choose which series are drawn: both, bandwidth only, or ping only."""
        mode = mode if mode in VIEW_MODES else VIEW_BOTH
        if mode == self._view_mode:
            return
        self._view_mode = mode
        self._apply_view_mode()
        self._redraw()

    def _apply_view_mode(self) -> None:
        """Show/hide the curves, markers and Y-axes for the current mode."""
        p = self.getPlotItem()
        show_bw = self._view_mode in (VIEW_BOTH, VIEW_BANDWIDTH)
        show_ping = self._view_mode in (VIEW_BOTH, VIEW_PING)

        for item in (self._down_curve, self._up_curve,
                     self._peak_down_line, self._avg_down_line,
                     self._peak_up_line, self._avg_up_line):
            item.setVisible(show_bw)
        self._latency_curve.setVisible(show_ping)

        # Hide the axis that belongs to a hidden series so the plot uses the
        # full width for whatever is left.
        (p.showAxis if show_bw else p.hideAxis)("left")
        (p.showAxis if show_ping else p.hideAxis)("right")

        # Showing/hiding an axis changes the plot geometry; keep the latency
        # viewbox aligned with it.
        self._sync_latency()

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
        self._down_curve.setPen(pg.mkPen(QColor(colors.download), width=1))
        self._down_curve.setBrush(
            pg.mkBrush(QColor(colors.fill_r, colors.fill_g, colors.fill_b, colors.fill_a))
        )
        self._up_curve.setPen(pg.mkPen(QColor(colors.upload), width=1))

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
        # The window changed wholesale, so jump to the new scale.
        self._redraw(snap_scale=True)

    def reset(self) -> None:
        self._download = deque([0.0] * self._history, maxlen=self._history)
        self._upload = deque([0.0] * self._history, maxlen=self._history)
        self._latency = deque([0.0] * self._history, maxlen=self._history)
        self._redraw(snap_scale=True)

    # ------------------------------------------------------------------ #
    #  Render                                                             #
    # ------------------------------------------------------------------ #

    def set_smooth_alpha(self, alpha: float) -> None:
        """Change the EMA smoothing factor (0.0 .. 1.0)."""
        self._smooth_alpha = max(0.0, min(1.0, alpha))
        self._redraw()

    def set_fill_enabled(self, enabled: bool) -> None:
        """Toggle the shaded area under the download curve."""
        if enabled == self._fill_enabled:
            return
        self._fill_enabled = enabled
        self._down_curve.setFillLevel(0 if enabled else None)

    def _redraw(self, snap_scale: bool = False) -> None:
        xs = self._xs
        dl_raw = list(self._download)
        ul_raw = list(self._upload)

        # Apply EMA smoothing for visually cleaner curves.
        alpha = self._smooth_alpha
        dl = _ema_smooth(dl_raw, alpha) if alpha < 1.0 else dl_raw
        ul = _ema_smooth(ul_raw, alpha) if alpha < 1.0 else ul_raw

        self._down_curve.setData(xs, dl)
        self._up_curve.setData(xs, ul)

        # Scale Y to the *raw* peak on screen so spikes aren't clipped and the
        # busiest moment in view sits at the top of the plot.  As that peak
        # scrolls out of the window the axis eases back down by itself.
        peak = max(max(dl_raw, default=0.0), max(ul_raw, default=0.0))
        self._rate_scaler.set_target(peak, snap=snap_scale)

        # Peak / average markers use raw data for accuracy.
        if dl_raw:
            self._peak_down_line.setValue(max(dl_raw))
            self._avg_down_line.setValue(sum(dl_raw) / len(dl_raw))
        if ul_raw:
            self._peak_up_line.setValue(max(ul_raw))
            self._avg_up_line.setValue(sum(ul_raw) / len(ul_raw))

        # Latency curve (secondary axis) — also smoothed.
        lat_raw = list(self._latency)
        lat = _ema_smooth(lat_raw, alpha) if alpha < 1.0 else lat_raw
        self._latency_curve.setData(xs, lat)
        self._latency_scaler.set_target(max(lat_raw, default=0.0), snap=snap_scale)
