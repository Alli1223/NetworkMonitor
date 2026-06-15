"""Entry point for Network Monitor.

Run from source:
    python main.py
    python main.py --debug      # extra-verbose logging

PyInstaller uses this same file as the script.
"""

from __future__ import annotations

import logging
import os
import sys
import tempfile

from src.logging_setup import setup_logging


def _run_selftest() -> int:
    """Probe the hardware backends and write results to a temp file.

    Used to verify a frozen (PyInstaller) build can load NVML and the bundled
    LibreHardwareMonitor DLLs from the extracted bundle.  The windowed exe has
    no console, so results go to %TEMP%\\nm_selftest.txt.
    """
    import time

    lines = []
    try:
        from src.system_monitor import SystemSampler

        s = SystemSampler()
        s.poll()
        time.sleep(0.3)
        smp = s.poll()
        lines.append(
            f"system OK cpu={smp.cpu_percent:.0f}% ram={smp.ram_percent:.0f}% "
            f"gpu_available={smp.gpu.available} gpu='{smp.gpu.name}' "
            f"gpu_util={smp.gpu.util_percent:.0f}% gpu_temp={smp.gpu.temp_c}"
        )
        s.close()
    except Exception as exc:
        lines.append(f"system ERROR {exc!r}")
    try:
        from src.temperature_monitor import TemperatureReader, is_admin

        r = TemperatureReader()
        ts = r.read()
        r.close()
        lines.append(
            f"temps available={ts.available} needs_admin={ts.needs_admin} "
            f"is_admin={is_admin()} cpu_c={ts.cpu_c} mobo_c={ts.mobo_c} "
            f"err={ts.error}"
        )
    except Exception as exc:
        lines.append(f"temps ERROR {exc!r}")

    out = os.path.join(tempfile.gettempdir(), "nm_selftest.txt")
    with open(out, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    return 0


def main() -> int:
    if "--selftest" in sys.argv:
        return _run_selftest()

    verbose = "--debug" in sys.argv or "-v" in sys.argv
    path = setup_logging(verbose=verbose)
    logging.info("argv=%s", sys.argv)

    try:
        # Imported AFTER logging is set up so any import-time errors are captured.
        from src.main_window import MainWindow, create_app

        app = create_app()
        window = MainWindow()
        # Tray-only first launch if requested
        if window._settings.start_minimized and window.tray.isVisible():  # type: ignore[attr-defined]
            window.hide()
            logging.info("Started minimized to tray.")
        else:
            window.show()
        rc = app.exec()
        logging.info("Event loop exited rc=%s", rc)
        return rc
    except SystemExit:
        raise
    except BaseException:
        # catch *everything*, including KeyboardInterrupt, so we get a log entry
        logging.exception("Fatal error during startup or main loop")
        try:
            from PyQt6.QtWidgets import QApplication, QMessageBox

            QApplication.instance() or QApplication(sys.argv)
            QMessageBox.critical(
                None,
                "Network Monitor crashed",
                f"An unexpected error occurred.\n\nDetails were written to:\n{path}",
            )
        except Exception:
            pass
        return 1


if __name__ == "__main__":
    sys.exit(main())
