"""Background latency measurement using TCP connect (no admin required)."""

from __future__ import annotations

import logging
import socket
import time

from PyQt6.QtCore import QThread, pyqtSignal

log = logging.getLogger(__name__)


class LatencyThread(QThread):
    """Measures TCP connect latency to a host in a background thread.

    Uses TCP connect to port 53 (DNS) by default, which works without
    elevated privileges unlike raw ICMP ping.
    """

    result = pyqtSignal(float)  # latency in ms; -1.0 on timeout/error

    def __init__(self, host: str = "8.8.8.8", port: int = 53,
                 interval_s: float = 2.0, parent=None):
        super().__init__(parent)
        self._host = host
        self._port = port
        self._interval = interval_s
        self._stop = False

    def set_host(self, host: str, port: int = 53) -> None:
        self._host = host
        self._port = port

    def run(self) -> None:
        while not self._stop:
            ms = self._tcp_ping()
            self.result.emit(ms)
            self.msleep(int(self._interval * 1000))

    def stop(self) -> None:
        self._stop = True
        self.wait(5000)

    def _tcp_ping(self) -> float:
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(2.0)
            start = time.perf_counter()
            sock.connect((self._host, self._port))
            elapsed_ms = (time.perf_counter() - start) * 1000
            sock.close()
            return round(elapsed_ms, 1)
        except (socket.timeout, OSError):
            return -1.0
