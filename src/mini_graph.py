"""Task-Manager-style mini-graph tile.

A compact, clickable widget showing a metric name, its current value, an
optional secondary line (e.g. temperature), and a small filled sparkline of
recent history.  Painted entirely with QPainter so it stays cheap to redraw
many times per second.
"""

from __future__ import annotations

from collections import deque
from typing import Deque, Optional

from PyQt6.QtCore import QRectF, Qt, pyqtSignal
from PyQt6.QtGui import (
    QColor,
    QFont,
    QMouseEvent,
    QPainter,
    QPainterPath,
    QPaintEvent,
    QPen,
)
from PyQt6.QtWidgets import QWidget

from .theme import ModeColors


class MiniGraphTile(QWidget):
    """A small live sparkline tile that behaves like a button.

    Values pushed via :meth:`push` are normalised against ``max_value`` (or
    auto-scaled to the rolling peak when ``max_value`` is None) and drawn as a
    filled area chart.  Emits :pyqtsignal:`clicked` on left mouse press.
    """

    clicked = pyqtSignal()

    def __init__(
        self,
        key: str,
        title: str,
        accent: str = "#4f9dff",
        max_value: Optional[float] = 100.0,
        capacity: int = 60,
        parent=None,
    ):
        super().__init__(parent)
        self.key = key
        self._title = title
        self._accent = QColor(accent)
        self._max_value = max_value
        self._values: Deque[float] = deque([0.0] * capacity, maxlen=capacity)
        self._value_text = "—"
        self._sub_text = ""
        self._selected = False

        # Theme-driven colours (sensible dark defaults until apply_theme runs).
        self._bg = QColor("#161b22")
        self._bg_sel = QColor("#21262d")
        self._border = QColor("#30363d")
        self._text_title = QColor("#c9d1d9")
        self._text_value = QColor("#f0f6fc")
        self._text_sub = QColor("#7d8590")

        self.setMinimumHeight(58)
        self.setMaximumHeight(64)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    # ------------------------------------------------------------------ #
    #  Public API                                                        #
    # ------------------------------------------------------------------ #

    def set_capacity(self, capacity: int) -> None:
        capacity = max(10, int(capacity))
        if capacity == self._values.maxlen:
            return
        old = list(self._values)[-capacity:]
        while len(old) < capacity:
            old.insert(0, 0.0)
        self._values = deque(old, maxlen=capacity)
        self.update()

    def push(self, value: float, value_text: Optional[str] = None,
             sub_text: Optional[str] = None) -> None:
        self._values.append(max(0.0, float(value)))
        if value_text is not None:
            self._value_text = value_text
        if sub_text is not None:
            self._sub_text = sub_text
        self.update()

    def set_sub_text(self, text: str) -> None:
        self._sub_text = text
        self.update()

    def set_selected(self, selected: bool) -> None:
        if selected != self._selected:
            self._selected = selected
            self.update()

    def set_accent(self, color: str) -> None:
        self._accent = QColor(color)
        self.update()

    def apply_theme(self, mode: ModeColors) -> None:
        self._bg = QColor(mode.bg_secondary)
        self._bg_sel = QColor(mode.bg_input)
        self._border = QColor(mode.border)
        self._text_title = QColor(mode.text_title)
        self._text_value = QColor(mode.text_bright)
        self._text_sub = QColor(mode.text_subtle)
        self.update()

    # ------------------------------------------------------------------ #
    #  Events                                                            #
    # ------------------------------------------------------------------ #

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)

    # ------------------------------------------------------------------ #
    #  Painting                                                          #
    # ------------------------------------------------------------------ #

    def paintEvent(self, event: QPaintEvent) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        r = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)

        # Card background + border (accent border when selected).
        p.setBrush(self._bg_sel if self._selected else self._bg)
        pen = QPen(self._accent if self._selected else self._border)
        pen.setWidthF(1.4 if self._selected else 1.0)
        p.setPen(pen)
        p.drawRoundedRect(r, 8.0, 8.0)

        # Sparkline occupies the lower portion, inset from the edges.
        pad = 8.0
        spark_top = r.top() + 26.0
        spark = QRectF(r.left() + pad, spark_top,
                       r.width() - 2 * pad, r.bottom() - spark_top - 5.0)
        if spark.height() > 4 and len(self._values) >= 2:
            self._draw_sparkline(p, spark)

        # Text on top of the sparkline.
        p.setClipping(False)
        title_font = QFont(self.font())
        title_font.setPointSizeF(8.5)
        title_font.setBold(True)
        p.setFont(title_font)
        p.setPen(self._text_title)
        p.drawText(
            QRectF(r.left() + pad, r.top() + 5.0, r.width() - 2 * pad, 16.0),
            int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter),
            self._title,
        )

        value_font = QFont(self.font())
        value_font.setPointSizeF(10.5)
        value_font.setBold(True)
        p.setFont(value_font)
        p.setPen(self._text_value)
        p.drawText(
            QRectF(r.left() + pad, r.top() + 4.0, r.width() - 2 * pad, 17.0),
            int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter),
            self._value_text,
        )

        if self._sub_text:
            sub_font = QFont(self.font())
            sub_font.setPointSizeF(7.5)
            p.setFont(sub_font)
            p.setPen(self._text_sub)
            p.drawText(
                QRectF(r.left() + pad, r.bottom() - 14.0, r.width() - 2 * pad, 12.0),
                int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter),
                self._sub_text,
            )
        p.end()

    def _draw_sparkline(self, p: QPainter, area: QRectF) -> None:
        vals = list(self._values)
        n = len(vals)
        peak = self._max_value if self._max_value is not None else max(vals)
        peak = max(peak, 1e-6)

        def point(i: int, v: float):
            x = area.left() + (area.width() * i / (n - 1))
            y = area.bottom() - (min(v / peak, 1.0) * area.height())
            return x, y

        path = QPainterPath()
        x0, y0 = point(0, vals[0])
        path.moveTo(x0, y0)
        for i in range(1, n):
            x, y = point(i, vals[i])
            path.lineTo(x, y)

        # Filled area under the line.
        fill = QPainterPath(path)
        fill.lineTo(area.right(), area.bottom())
        fill.lineTo(area.left(), area.bottom())
        fill.closeSubpath()
        fill_color = QColor(self._accent)
        fill_color.setAlpha(55)
        p.fillPath(fill, fill_color)

        # The line itself (1px).
        line_pen = QPen(self._accent)
        line_pen.setWidthF(1.0)
        line_pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        p.setPen(line_pen)
        p.drawPath(path)
