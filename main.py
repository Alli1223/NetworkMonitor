"""Entry point for Network Monitor.

Run from source:
    python main.py
    python main.py --debug      # extra-verbose logging

PyInstaller uses this same file as the script.
"""

from __future__ import annotations

import logging
import sys

from src.logging_setup import setup_logging


def main() -> int:
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
