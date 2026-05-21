"""Main application window: graph + controls + status bar + tray."""

from __future__ import annotations

import logging
import os
import sys
from typing import Optional

log = logging.getLogger(__name__)

from PyQt6.QtCore import QSize, Qt, QTimer
from PyQt6.QtGui import QAction, QCloseEvent, QIcon, QPixmap
from PyQt6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMenu,
    QMessageBox,
    QProgressDialog,
    QPushButton,
    QSpinBox,
    QStatusBar,
    QSystemTrayIcon,
    QVBoxLayout,
    QWidget,
)

from .graph_widget import DOWNLOAD_COLOR, UPLOAD_COLOR, TrafficGraph
from .network_monitor import (
    InterfaceInfo,
    NetworkSampler,
    format_bytes,
    format_rate,
    list_interfaces,
)
from .settings import AppSettings, SettingsStore
from .style import DARK_QSS
from .updater import (
    DownloadWorker,
    ReleaseInfo,
    UpdateCheckWorker,
    is_newer,
    launch_installer,
    run_in_thread,
)
from .version import APP_NAME, __version__


def _asset_path(filename: str) -> str:
    """Resolve assets both when running from source and from a PyInstaller bundle."""
    base = getattr(sys, "_MEIPASS", None)
    if base:
        return os.path.join(base, "assets", filename)
    here = os.path.dirname(os.path.abspath(__file__))
    return os.path.normpath(os.path.join(here, "..", "assets", filename))


def load_app_icon() -> QIcon:
    """Load icon.svg as a QIcon, with sensible fallbacks at common tray sizes."""
    icon = QIcon(_asset_path("icon.svg"))
    if icon.isNull():
        # Build a tiny fallback so the app still has an icon.
        pix = QPixmap(64, 64)
        pix.fill(Qt.GlobalColor.transparent)
        icon = QIcon(pix)
    return icon


# ---------------------------------------------------------------------------
# Settings dialog
# ---------------------------------------------------------------------------


class SettingsDialog(QDialog):
    def __init__(self, current: AppSettings, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Settings")
        self.setModal(True)
        self.setMinimumWidth(360)

        self.history_spin = QSpinBox()
        self.history_spin.setRange(15, 600)
        self.history_spin.setSuffix(" s")
        self.history_spin.setValue(current.history_seconds)

        self.interval_spin = QSpinBox()
        self.interval_spin.setRange(250, 10_000)
        self.interval_spin.setSingleStep(250)
        self.interval_spin.setSuffix(" ms")
        self.interval_spin.setValue(current.update_interval_ms)

        self.start_min_chk = QCheckBox("Start minimized to tray")
        self.start_min_chk.setChecked(current.start_minimized)

        self.close_to_tray_chk = QCheckBox("Closing the window minimizes to tray")
        self.close_to_tray_chk.setChecked(current.minimize_to_tray_on_close)

        self.check_updates_chk = QCheckBox("Check for updates on startup")
        self.check_updates_chk.setChecked(current.check_updates_on_start)

        grid = QGridLayout()
        grid.addWidget(QLabel("Graph history"), 0, 0)
        grid.addWidget(self.history_spin, 0, 1)
        grid.addWidget(QLabel("Update interval"), 1, 0)
        grid.addWidget(self.interval_spin, 1, 1)
        grid.addWidget(self.start_min_chk, 2, 0, 1, 2)
        grid.addWidget(self.close_to_tray_chk, 3, 0, 1, 2)
        grid.addWidget(self.check_updates_chk, 4, 0, 1, 2)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(grid)
        layout.addStretch(1)
        layout.addWidget(buttons)

    def apply_to(self, s: AppSettings) -> AppSettings:
        s.history_seconds = self.history_spin.value()
        s.update_interval_ms = self.interval_spin.value()
        s.start_minimized = self.start_min_chk.isChecked()
        s.minimize_to_tray_on_close = self.close_to_tray_chk.isChecked()
        s.check_updates_on_start = self.check_updates_chk.isChecked()
        return s


# ---------------------------------------------------------------------------
# Main window
# ---------------------------------------------------------------------------


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle(APP_NAME)
        self.setWindowIcon(load_app_icon())
        self.setMinimumSize(QSize(420, 260))
        self.resize(520, 320)

        self._store = SettingsStore()
        self._settings: AppSettings = self._store.load()
        self._sampler: Optional[NetworkSampler] = None
        self._force_quit = False

        # Keep refs to threads so they aren't GC'd mid-flight.
        self._update_thread = None
        self._update_worker: Optional[UpdateCheckWorker] = None
        self._download_thread = None
        self._download_worker: Optional[DownloadWorker] = None

        self._build_ui()
        self._build_tray()
        self._populate_interfaces()
        self._restore_window_state()

        # Timer drives sampling and graph updates.
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(self._settings.update_interval_ms)

        if self._settings.check_updates_on_start:
            QTimer.singleShot(2500, lambda: self._check_for_updates(silent=True))

    # ------------------------------ UI build --------------------------------

    def _build_ui(self) -> None:
        central = QWidget(self)
        central.setObjectName("central")
        self.setCentralWidget(central)

        outer = QVBoxLayout(central)
        outer.setContentsMargins(12, 12, 12, 12)
        outer.setSpacing(10)

        # Top row: interface picker + settings button
        top_row = QHBoxLayout()
        top_row.setSpacing(8)
        top_label = QLabel("Interface")
        top_label.setObjectName("subtle")
        self.iface_combo = QComboBox()
        self.iface_combo.setMinimumWidth(200)
        self.iface_combo.currentIndexChanged.connect(self._on_interface_changed)

        self.refresh_btn = QPushButton("Refresh")
        self.refresh_btn.clicked.connect(self._populate_interfaces)

        self.settings_btn = QPushButton("Settings")
        self.settings_btn.clicked.connect(self._open_settings)

        top_row.addWidget(top_label)
        top_row.addWidget(self.iface_combo, 1)
        top_row.addWidget(self.refresh_btn)
        top_row.addWidget(self.settings_btn)
        outer.addLayout(top_row)

        # Metric cards row
        cards_row = QHBoxLayout()
        cards_row.setSpacing(10)
        self.down_card, self.down_value, self.down_total = self._build_metric_card(
            "Download", DOWNLOAD_COLOR, "downAccent"
        )
        self.up_card, self.up_value, self.up_total = self._build_metric_card(
            "Upload", UPLOAD_COLOR, "upAccent"
        )
        cards_row.addWidget(self.down_card, 1)
        cards_row.addWidget(self.up_card, 1)
        outer.addLayout(cards_row)

        # Graph card
        graph_card = QFrame()
        graph_card.setObjectName("card")
        graph_layout = QVBoxLayout(graph_card)
        graph_layout.setContentsMargins(8, 8, 8, 8)
        self.graph = TrafficGraph(history_seconds=self._settings.history_seconds)
        graph_layout.addWidget(self.graph)
        outer.addWidget(graph_card, 1)

        # Status bar
        self.setStatusBar(QStatusBar())
        self.statusBar().showMessage(f"v{__version__}")

    def _build_metric_card(self, title: str, color: str, accent_object_name: str):
        card = QFrame()
        card.setObjectName("card")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(2)

        header = QHBoxLayout()
        swatch = QLabel()
        swatch.setFixedSize(10, 10)
        swatch.setStyleSheet(f"background-color: {color}; border-radius: 5px;")
        title_lbl = QLabel(title)
        title_lbl.setObjectName("title")
        header.addWidget(swatch)
        header.addWidget(title_lbl)
        header.addStretch(1)
        layout.addLayout(header)

        value_lbl = QLabel("0 B/s")
        value_lbl.setObjectName("bigMetric")
        value_lbl.setProperty("class", accent_object_name)
        # Use objectName for QSS color rule
        value_lbl.setObjectName(accent_object_name)
        layout.addWidget(value_lbl)

        total_lbl = QLabel("Total: 0 B")
        total_lbl.setObjectName("subtle")
        layout.addWidget(total_lbl)

        return card, value_lbl, total_lbl

    def _build_tray(self) -> None:
        self.tray = QSystemTrayIcon(load_app_icon(), self)
        self.tray.setToolTip(APP_NAME)

        menu = QMenu()
        show_act = QAction("Show window", self)
        show_act.triggered.connect(self._show_from_tray)
        hide_act = QAction("Hide window", self)
        hide_act.triggered.connect(self.hide)
        check_act = QAction("Check for updates", self)
        check_act.triggered.connect(lambda: self._check_for_updates(silent=False))
        about_act = QAction(f"About {APP_NAME}", self)
        about_act.triggered.connect(self._show_about)
        quit_act = QAction("Quit", self)
        quit_act.triggered.connect(self._quit_application)

        menu.addAction(show_act)
        menu.addAction(hide_act)
        menu.addSeparator()
        menu.addAction(check_act)
        menu.addAction(about_act)
        menu.addSeparator()
        menu.addAction(quit_act)

        self.tray.setContextMenu(menu)
        self.tray.activated.connect(self._on_tray_activated)
        self.tray.show()

    # ----------------------------- Interfaces -------------------------------

    def _populate_interfaces(self) -> None:
        previous = self.iface_combo.currentData() if self.iface_combo.count() else self._settings.interface
        self.iface_combo.blockSignals(True)
        self.iface_combo.clear()
        interfaces = list_interfaces()
        for info in interfaces:
            label = self._iface_label(info)
            self.iface_combo.addItem(label, userData=info.name)

        # Pick the previously selected interface, or the first "up with IP", or index 0.
        target_index = -1
        if previous:
            for i in range(self.iface_combo.count()):
                if self.iface_combo.itemData(i) == previous:
                    target_index = i
                    break
        if target_index < 0:
            for i, info in enumerate(interfaces):
                if info.is_up and info.addresses:
                    target_index = i
                    break
        if target_index < 0 and interfaces:
            target_index = 0
        if target_index >= 0:
            self.iface_combo.setCurrentIndex(target_index)
        self.iface_combo.blockSignals(False)
        self._on_interface_changed()

    @staticmethod
    def _iface_label(info: InterfaceInfo) -> str:
        bits = [info.display_name]
        status = "up" if info.is_up else "down"
        if info.speed_mbps:
            bits.append(f"{info.speed_mbps} Mb/s")
        bits.append(status)
        if info.addresses:
            bits.append(info.addresses[0])
        return "  ·  ".join(bits)

    def _on_interface_changed(self) -> None:
        name = self.iface_combo.currentData()
        if not name:
            return
        if self._sampler is None:
            self._sampler = NetworkSampler(name)
        else:
            self._sampler.set_interface(name)
        self.graph.reset()
        self.down_value.setText("0 B/s")
        self.up_value.setText("0 B/s")
        self._settings.interface = name
        self._store.save(self._settings)
        self.statusBar().showMessage(f"Monitoring {name}  ·  v{__version__}")

    # -------------------------------- Tick ----------------------------------

    def _tick(self) -> None:
        # Wrap in try/except so a single bad poll cannot kill the app.
        try:
            if self._sampler is None:
                return
            rate = self._sampler.poll()
            if rate is None:
                self.statusBar().showMessage(
                    f"Interface '{self._sampler.interface}' unavailable  ·  v{__version__}"
                )
                return
            self.graph.add_sample(rate.download_bps, rate.upload_bps)
            self.down_value.setText(format_rate(rate.download_bps))
            self.up_value.setText(format_rate(rate.upload_bps))
            self.down_total.setText(f"Total: {format_bytes(rate.total_recv)}")
            self.up_total.setText(f"Total: {format_bytes(rate.total_sent)}")
            self.tray.setToolTip(
                f"{APP_NAME}\n"
                f"↓ {format_rate(rate.download_bps)}   "
                f"↑ {format_rate(rate.upload_bps)}"
            )
        except Exception:
            log.exception("Tick failed (will keep running)")

    # ------------------------------ Settings --------------------------------

    def _open_settings(self) -> None:
        dlg = SettingsDialog(self._settings, parent=self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self._settings = dlg.apply_to(self._settings)
            self._store.save(self._settings)
            self._timer.setInterval(self._settings.update_interval_ms)
            self.graph.set_history_seconds(self._settings.history_seconds)

    # -------------------------------- Tray ----------------------------------

    def _on_tray_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason in (
            QSystemTrayIcon.ActivationReason.Trigger,
            QSystemTrayIcon.ActivationReason.DoubleClick,
        ):
            self._show_from_tray()

    def _show_from_tray(self) -> None:
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def _quit_application(self) -> None:
        self._force_quit = True
        # Stop sampling timer first, then wait briefly for any worker threads.
        try:
            self._timer.stop()
        except Exception:  # noqa: BLE001
            pass
        for t in (self._update_thread, self._download_thread):
            try:
                if t is not None and t.isRunning():
                    t.quit()
                    t.wait(1500)
            except Exception:  # noqa: BLE001
                pass
        self.close()
        QApplication.instance().quit()

    # ------------------------------- Updates --------------------------------

    def _check_for_updates(self, silent: bool) -> None:
        if self._update_worker is not None:
            return  # already in flight
        log.info("Checking for updates (silent=%s)", silent)
        worker = UpdateCheckWorker()
        worker.finished.connect(
            lambda info, err: self._on_update_check_done(info, err, silent)
        )
        thread = run_in_thread(worker)
        # Release refs only once the thread has fully shut down — otherwise
        # we can hit "QThread destroyed while still running" on Windows.
        thread.finished.connect(self._release_update_refs)
        self._update_worker = worker
        self._update_thread = thread
        if not silent:
            self.statusBar().showMessage("Checking for updates…")

    def _release_update_refs(self) -> None:
        self._update_worker = None
        self._update_thread = None

    def _on_update_check_done(
        self, info: Optional[ReleaseInfo], err: Optional[str], silent: bool
    ) -> None:
        log.info("Update check done (err=%s, info=%s)",
                 err, info.tag if info else None)
        if err:
            if not silent:
                QMessageBox.warning(self, "Update check failed", err)
            return
        if info is None:
            if not silent:
                QMessageBox.information(
                    self, "No releases", "No published releases were found for this app."
                )
            return
        if not is_newer(info):
            if not silent:
                QMessageBox.information(
                    self, "You're up to date",
                    f"You are running the latest version (v{__version__}).",
                )
            return
        asset = info.pick_asset()
        if asset is None:
            QMessageBox.warning(
                self, "Update available",
                f"Version {info.tag} is available, but no installer for this platform "
                f"was found in the release.\n\nVisit {info.html_url}",
            )
            return

        reply = QMessageBox.question(
            self,
            "Update available",
            (
                f"<b>{info.name}</b> is available "
                f"(you have v{__version__}).<br><br>"
                f"Download and install <code>{asset.name}</code> "
                f"({asset.size // 1024} KB) now?"
            ),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        self._begin_download(asset)

    def _begin_download(self, asset) -> None:
        progress = QProgressDialog("Downloading update…", "Cancel", 0, 100, self)
        progress.setWindowTitle("Updating")
        progress.setWindowModality(Qt.WindowModality.WindowModal)
        progress.setAutoClose(False)
        progress.setAutoReset(False)
        progress.setValue(0)

        worker = DownloadWorker(asset)

        def on_progress(done: int, total: int) -> None:
            if total <= 0:
                return
            progress.setValue(int(done * 100 / total))

        def on_finished(path: Optional[str], err: Optional[str]) -> None:
            progress.close()
            if err or not path:
                QMessageBox.warning(self, "Download failed", err or "Unknown error")
                return
            QMessageBox.information(
                self, "Installing update",
                "The installer will now launch and the app will exit.",
            )
            try:
                launch_installer(path)
            except Exception as exc:  # noqa: BLE001
                QMessageBox.warning(self, "Could not launch installer", str(exc))
                return
            self._quit_application()

        worker.progress.connect(on_progress)
        worker.finished.connect(on_finished)
        progress.canceled.connect(lambda: None)  # best-effort; download isn't interruptible

        thread = run_in_thread(worker)
        thread.finished.connect(self._release_download_refs)
        self._download_worker = worker
        self._download_thread = thread

    def _release_download_refs(self) -> None:
        self._download_worker = None
        self._download_thread = None

    def _show_about(self) -> None:
        QMessageBox.about(
            self,
            f"About {APP_NAME}",
            f"<b>{APP_NAME}</b><br>"
            f"Version {__version__}<br><br>"
            f"A lightweight cross-platform network traffic monitor.",
        )

    # ----------------------------- Window state -----------------------------

    def _restore_window_state(self) -> None:
        if self._settings.window_geometry:
            try:
                self.restoreGeometry(self._settings.window_geometry)
            except Exception:  # noqa: BLE001
                pass
        if self._settings.window_state:
            try:
                self.restoreState(self._settings.window_state)
            except Exception:  # noqa: BLE001
                pass

    def _save_window_state(self) -> None:
        self._settings.window_geometry = bytes(self.saveGeometry())
        self._settings.window_state = bytes(self.saveState())
        self._store.save(self._settings)

    # ----------------------------- Close handling ---------------------------

    def closeEvent(self, event: QCloseEvent) -> None:
        self._save_window_state()
        if self._force_quit or not self._settings.minimize_to_tray_on_close:
            event.accept()
            return
        # Minimize to tray instead of quitting
        event.ignore()
        self.hide()
        if self.tray.isVisible():
            self.tray.showMessage(
                APP_NAME,
                "Still running in the system tray. Right-click the tray icon to quit.",
                load_app_icon(),
                3000,
            )


def create_app() -> QApplication:
    app = QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setOrganizationName("NetworkMonitor")
    app.setQuitOnLastWindowClosed(False)  # tray keeps us alive
    app.setStyleSheet(DARK_QSS)
    app.setWindowIcon(load_app_icon())
    return app
