r"""Crash-safe logging and exception capture.

Logs go to:
  Windows: %APPDATA%\NetworkMonitor\networkmonitor.log
  Linux:   ~/.local/share/NetworkMonitor/networkmonitor.log

Also installs a `sys.excepthook` and a Qt message handler so otherwise-silent
errors (especially when running via pythonw.exe) end up in the log file.
"""

from __future__ import annotations

import logging
import os
import platform
import sys
import traceback
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Optional


_LOG_PATH: Optional[Path] = None


def log_dir() -> Path:
    """Per-user writable directory for the log file."""
    if platform.system().lower() == "windows":
        base = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
        path = Path(base) / "NetworkMonitor"
    else:
        base = os.environ.get("XDG_DATA_HOME") or str(Path.home() / ".local" / "share")
        path = Path(base) / "NetworkMonitor"
    path.mkdir(parents=True, exist_ok=True)
    return path


def log_path() -> Path:
    global _LOG_PATH
    if _LOG_PATH is None:
        _LOG_PATH = log_dir() / "networkmonitor.log"
    return _LOG_PATH


def setup_logging(verbose: bool = False) -> Path:
    """Configure root logger + global exception hooks. Returns the log file path."""
    path = log_path()
    level = logging.DEBUG if verbose else logging.INFO

    handler = RotatingFileHandler(path, maxBytes=512_000, backupCount=3, encoding="utf-8")
    handler.setFormatter(logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    ))
    root = logging.getLogger()
    root.setLevel(level)
    # Remove any prior handlers (e.g. on re-init) to avoid duplicates.
    for h in list(root.handlers):
        root.removeHandler(h)
    root.addHandler(handler)

    # Also log to stderr when a console is attached (run.bat debug mode, terminal).
    if sys.stderr and sys.stderr.isatty():
        sh = logging.StreamHandler()
        sh.setFormatter(logging.Formatter("%(levelname)s: %(message)s"))
        root.addHandler(sh)

    logging.info("=" * 60)
    logging.info("Network Monitor starting (python=%s, platform=%s)",
                 sys.version.split()[0], platform.platform())
    logging.info("Log file: %s", path)

    def _excepthook(exc_type, exc_value, exc_tb):
        logging.critical("UNCAUGHT EXCEPTION:\n%s",
                         "".join(traceback.format_exception(exc_type, exc_value, exc_tb)))
        # Still call the default hook so it surfaces if there is a console.
        sys.__excepthook__(exc_type, exc_value, exc_tb)

    sys.excepthook = _excepthook

    # Qt has its own message stream; route it into the same log.
    try:
        from PyQt6.QtCore import QtMsgType, qInstallMessageHandler

        _MAP = {
            QtMsgType.QtDebugMsg: logging.DEBUG,
            QtMsgType.QtInfoMsg: logging.INFO,
            QtMsgType.QtWarningMsg: logging.WARNING,
            QtMsgType.QtCriticalMsg: logging.ERROR,
            QtMsgType.QtFatalMsg: logging.CRITICAL,
        }

        def _qt_handler(mode, context, message):
            lvl = _MAP.get(mode, logging.INFO)
            where = ""
            if context and context.file:
                where = f" ({context.file}:{context.line})"
                if context.function:
                    where += f" in {context.function}"
            logging.log(lvl, "Qt%s: %s%s", _qt_level_name(mode), message, where)

        qInstallMessageHandler(_qt_handler)
    except Exception as exc:  # noqa: BLE001
        logging.warning("Could not install Qt message handler: %s", exc)

    return path


def _qt_level_name(mode) -> str:
    name = getattr(mode, "name", str(mode))
    return name.replace("Msg", "")
