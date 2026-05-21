"""Main application window: minimal top row + large live graph + tray."""

from __future__ import annotations

import logging
import os
import sys
from typing import Optional

log = logging.getLogger(__name__)

from PyQt6.QtCore import QSize, Qt, QTimer
from PyQt6.QtGui import QAction, QCloseEvent, QIcon, QMoveEvent, QPixmap, QResizeEvent
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
    QSlider,
    QSpinBox,
    QStatusBar,
    QSystemTrayIcon,
    QVBoxLayout,
    QWidget,
)

from .graph_widget import TrafficGraph
from .network_monitor import (
    InterfaceInfo,
    NetworkSampler,
    format_bytes,
    format_rate,
    list_interfaces,
)
from .settings import AppSettings, SettingsStore
from .style import generate_qss
from .theme import COLOR_THEMES, MODES
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
    """Load icon.svg as a QIcon, with a tiny fallback."""
    icon = QIcon(_asset_path("icon.svg"))
    if icon.isNull():
        pix = QPixmap(64, 64)
        pix.fill(Qt.GlobalColor.transparent)
        icon = QIcon(pix)
    return icon


# ---------------------------------------------------------------------------
# Settings dialog
# ---------------------------------------------------------------------------


class SettingsDialog(QDialog):
    """Settings dialog. Includes interface picker and all preferences."""

    def __init__(self, current: AppSettings, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Settings")
        self.setModal(True)
        self.setMinimumWidth(380)

        # Interface picker (populated with whatever exists right now).
        self.iface_combo = QComboBox()
        self.iface_combo.setMinimumWidth(220)
        self.refresh_btn = QPushButton("Refresh")
        self.refresh_btn.clicked.connect(self._reload_interfaces)
        iface_row = QHBoxLayout()
        iface_row.addWidget(self.iface_combo, 1)
        iface_row.addWidget(self.refresh_btn)

        self.history_spin = QSpinBox()
        self.history_spin.setRange(15, 600)
        self.history_spin.setSuffix(" s")
        self.history_spin.setValue(current.history_seconds)

        self.interval_spin = QSpinBox()
        self.interval_spin.setRange(250, 10_000)
        self.interval_spin.setSingleStep(250)
        self.interval_spin.setSuffix(" ms")
        self.interval_spin.setValue(current.update_interval_ms)

        # Window transparency: 30..100 percent. Below 30 the window becomes
        # essentially invisible and uninteractive.
        self.opacity_slider = QSlider(Qt.Orientation.Horizontal)
        self.opacity_slider.setRange(30, 100)
        self.opacity_slider.setValue(max(30, min(100, current.window_opacity)))
        self.opacity_value_lbl = QLabel(f"{self.opacity_slider.value()}%")
        self.opacity_value_lbl.setMinimumWidth(40)
        self.opacity_slider.valueChanged.connect(
            lambda v: self.opacity_value_lbl.setText(f"{v}%")
        )
        opacity_row = QHBoxLayout()
        opacity_row.addWidget(self.opacity_slider, 1)
        opacity_row.addWidget(self.opacity_value_lbl)

        self.always_on_top_chk = QCheckBox("Always on top")
        self.always_on_top_chk.setChecked(current.always_on_top)

        self.start_min_chk = QCheckBox("Start minimized to tray")
        self.start_min_chk.setChecked(current.start_minimized)

        self.close_to_tray_chk = QCheckBox("Closing the window minimizes to tray")
        self.close_to_tray_chk.setChecked(current.minimize_to_tray_on_close)

        self.check_updates_chk = QCheckBox("Check for updates on startup")
        self.check_updates_chk.setChecked(current.check_updates_on_start)

        self.mode_combo = QComboBox()
        for key, mode in MODES.items():
            self.mode_combo.addItem(key.capitalize(), userData=key)
        idx = self.mode_combo.findData(current.theme_mode)
        if idx >= 0:
            self.mode_combo.setCurrentIndex(idx)

        self.color_theme_combo = QComboBox()
        for key, theme in COLOR_THEMES.items():
            self.color_theme_combo.addItem(theme.label, userData=key)
        idx = self.color_theme_combo.findData(current.color_theme)
        if idx >= 0:
            self.color_theme_combo.setCurrentIndex(idx)

        grid = QGridLayout()
        grid.setColumnStretch(1, 1)
        grid.setVerticalSpacing(8)
        row = 0
        grid.addWidget(QLabel("Interface"), row, 0)
        grid.addLayout(iface_row, row, 1)
        row += 1
        grid.addWidget(QLabel("Graph history"), row, 0)
        grid.addWidget(self.history_spin, row, 1)
        row += 1
        grid.addWidget(QLabel("Update interval"), row, 0)
        grid.addWidget(self.interval_spin, row, 1)
        row += 1
        grid.addWidget(QLabel("Transparency"), row, 0)
        grid.addLayout(opacity_row, row, 1)
        row += 1
        grid.addWidget(QLabel("Mode"), row, 0)
        grid.addWidget(self.mode_combo, row, 1)
        row += 1
        grid.addWidget(QLabel("Color theme"), row, 0)
        grid.addWidget(self.color_theme_combo, row, 1)
        row += 1
        grid.addWidget(self.always_on_top_chk, row, 0, 1, 2)
        row += 1
        grid.addWidget(self.start_min_chk, row, 0, 1, 2)
        row += 1
        grid.addWidget(self.close_to_tray_chk, row, 0, 1, 2)
        row += 1
        grid.addWidget(self.check_updates_chk, row, 0, 1, 2)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(grid)
        layout.addStretch(1)
        layout.addWidget(buttons)

        # Populate interfaces with currently saved selection preselected.
        self._reload_interfaces(preferred=current.interface)

    # ----- interface helpers -----

    def _reload_interfaces(self, preferred: Optional[str] = None) -> None:
        if preferred is None:
            preferred = self.iface_combo.currentData()
        self.iface_combo.blockSignals(True)
        self.iface_combo.clear()
        interfaces = list_interfaces()
        chosen_index = -1
        for i, info in enumerate(interfaces):
            self.iface_combo.addItem(_iface_label(info), userData=info.name)
            if preferred and info.name == preferred:
                chosen_index = i
        if chosen_index < 0:
            for i, info in enumerate(interfaces):
                if info.is_up and info.addresses:
                    chosen_index = i
                    break
        if chosen_index < 0 and interfaces:
            chosen_index = 0
        if chosen_index >= 0:
            self.iface_combo.setCurrentIndex(chosen_index)
        self.iface_combo.blockSignals(False)

    def selected_interface(self) -> Optional[str]:
        return self.iface_combo.currentData()

    def apply_to(self, s: AppSettings) -> AppSettings:
        s.interface = self.selected_interface()
        s.history_seconds = self.history_spin.value()
        s.update_interval_ms = self.interval_spin.value()
        s.window_opacity = self.opacity_slider.value()
        s.always_on_top = self.always_on_top_chk.isChecked()
        s.start_minimized = self.start_min_chk.isChecked()
        s.minimize_to_tray_on_close = self.close_to_tray_chk.isChecked()
        s.check_updates_on_start = self.check_updates_chk.isChecked()
        s.theme_mode = self.mode_combo.currentData()
        s.color_theme = self.color_theme_combo.currentData()
        return s


def _iface_label(info: InterfaceInfo) -> str:
    """Short, readable interface label for the combobox."""
    bits = [info.display_name]
    status = "up" if info.is_up else "down"
    if info.speed_mbps:
        bits.append(f"{info.speed_mbps} Mb/s")
    bits.append(status)
    if info.addresses:
        bits.append(info.addresses[0])
    return "  ·  ".join(bits)


# ---------------------------------------------------------------------------
# Main window
# ---------------------------------------------------------------------------


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle(APP_NAME)
        self.setWindowIcon(load_app_icon())
        self.setMinimumSize(QSize(320, 180))
        self.resize(440, 240)

        self._store = SettingsStore()
        self._settings: AppSettings = self._store.load()
        self._sampler: Optional[NetworkSampler] = None
        self._force_quit = False
        self._frameless = False

        # Workers / threads kept alive while they run.
        self._update_thread = None
        self._update_worker: Optional[UpdateCheckWorker] = None
        self._download_thread = None
        self._download_worker: Optional[DownloadWorker] = None

        # Debounce timer for saving geometry after a move/resize.
        self._geom_save_timer = QTimer(self)
        self._geom_save_timer.setSingleShot(True)
        self._geom_save_timer.setInterval(500)
        self._geom_save_timer.timeout.connect(self._save_window_state)

        self._build_ui()
        self._build_tray()
        self._apply_window_flags()
        self._apply_opacity()
        self._restore_window_state()
        self._initialise_sampler(self._settings.interface)

        # Sampling timer.
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
        outer.setContentsMargins(10, 8, 10, 8)
        outer.setSpacing(6)

        # ---- Top row: ↓ rate, ↑ rate, gear button --------------------------
        top_row = QHBoxLayout()
        top_row.setSpacing(10)

        self.down_arrow = QLabel("↓")
        self.down_arrow.setObjectName("downAccent")
        self.down_value = QLabel("0 B/s")
        self.down_value.setObjectName("inlineMetric")

        self.up_arrow = QLabel("↑")
        self.up_arrow.setObjectName("upAccent")
        self.up_value = QLabel("0 B/s")
        self.up_value.setObjectName("inlineMetric")

        # Separator dot between down and up
        sep = QLabel("·")
        sep.setObjectName("subtle")

        # Status text (subtle, small) — interface name
        self.status_lbl = QLabel("")
        self.status_lbl.setObjectName("subtle")

        # Settings gear button
        self.settings_btn = QPushButton("⚙")  # ⚙
        self.settings_btn.setObjectName("iconBtn")
        self.settings_btn.setToolTip("Settings")
        self.settings_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.settings_btn.clicked.connect(self._open_settings)

        top_row.addWidget(self.down_arrow)
        top_row.addWidget(self.down_value)
        top_row.addSpacing(4)
        top_row.addWidget(sep)
        top_row.addSpacing(4)
        top_row.addWidget(self.up_arrow)
        top_row.addWidget(self.up_value)
        top_row.addSpacing(12)
        top_row.addWidget(self.status_lbl, 1)  # stretches
        top_row.addWidget(self.settings_btn)
        outer.addLayout(top_row)

        # ---- Graph -----------------------------------------------------------
        graph_card = QFrame()
        graph_card.setObjectName("card")
        graph_layout = QVBoxLayout(graph_card)
        graph_layout.setContentsMargins(6, 6, 6, 6)
        self.graph = TrafficGraph(history_seconds=self._settings.history_seconds)
        self.graph.double_clicked.connect(self._toggle_frameless)
        graph_layout.addWidget(self.graph)
        outer.addWidget(graph_card, 1)

        self._apply_theme()

    def _build_tray(self) -> None:
        self.tray = QSystemTrayIcon(load_app_icon(), self)
        self.tray.setToolTip(APP_NAME)

        menu = QMenu()
        show_act = QAction("Show window", self)
        show_act.triggered.connect(self._show_from_tray)
        hide_act = QAction("Hide window", self)
        hide_act.triggered.connect(self.hide)
        settings_act = QAction("Settings…", self)
        settings_act.triggered.connect(self._open_settings)
        check_act = QAction("Check for updates", self)
        check_act.triggered.connect(lambda: self._check_for_updates(silent=False))
        about_act = QAction(f"About {APP_NAME}", self)
        about_act.triggered.connect(self._show_about)
        quit_act = QAction("Quit", self)
        quit_act.triggered.connect(self._quit_application)

        menu.addAction(show_act)
        menu.addAction(hide_act)
        menu.addSeparator()
        menu.addAction(settings_act)
        menu.addAction(check_act)
        menu.addAction(about_act)
        menu.addSeparator()
        menu.addAction(quit_act)

        self.tray.setContextMenu(menu)
        self.tray.activated.connect(self._on_tray_activated)
        self.tray.show()

    # ------------------------------ Window flags ----------------------------

    def _apply_window_flags(self) -> None:
        """Apply 'always on top' and frameless hints (rebuilding flags requires re-show)."""
        flags = self.windowFlags()
        if self._settings.always_on_top:
            flags |= Qt.WindowType.WindowStaysOnTopHint
        else:
            flags &= ~Qt.WindowType.WindowStaysOnTopHint
        if self._frameless:
            flags |= Qt.WindowType.FramelessWindowHint
        else:
            flags &= ~Qt.WindowType.FramelessWindowHint
        # setWindowFlags hides the window; save and restore geometry so the
        # window doesn't jump when the title bar appears / disappears.
        was_visible = self.isVisible()
        geom = self.geometry()
        self.setWindowFlags(flags)
        self.setGeometry(geom)
        if was_visible:
            self.show()

    def _toggle_frameless(self) -> None:
        """Toggle the window title bar on/off (double-click on graph)."""
        self._frameless = not self._frameless
        self._apply_window_flags()

    def _apply_opacity(self) -> None:
        """Map 30..100 percent setting onto setWindowOpacity()."""
        pct = max(30, min(100, int(self._settings.window_opacity)))
        self.setWindowOpacity(pct / 100.0)

    # ----------------------------- Interfaces -------------------------------

    def _initialise_sampler(self, interface_name: Optional[str]) -> None:
        """Pick a sampler interface: requested, or first up-with-IP, or first."""
        candidates = list_interfaces()
        chosen: Optional[str] = None
        if interface_name:
            for info in candidates:
                if info.name == interface_name:
                    chosen = info.name
                    break
        if chosen is None:
            for info in candidates:
                if info.is_up and info.addresses:
                    chosen = info.name
                    break
        if chosen is None and candidates:
            chosen = candidates[0].name
        if chosen is None:
            self.status_lbl.setText("No network interfaces found")
            return
        if self._sampler is None:
            self._sampler = NetworkSampler(chosen)
        else:
            self._sampler.set_interface(chosen)
        self._settings.interface = chosen
        self._store.save(self._settings)
        self.graph.reset()
        self.down_value.setText("0 B/s")
        self.up_value.setText("0 B/s")
        self.status_lbl.setText(f"{chosen}  ·  v{__version__}")

    # -------------------------------- Tick ----------------------------------

    def _tick(self) -> None:
        try:
            if self._sampler is None:
                return
            rate = self._sampler.poll()
            if rate is None:
                self.status_lbl.setText(
                    f"{self._sampler.interface} (unavailable)  ·  v{__version__}"
                )
                return
            self.graph.add_sample(rate.download_bps, rate.upload_bps)
            self.down_value.setText(format_rate(rate.download_bps))
            self.up_value.setText(format_rate(rate.upload_bps))
            self.tray.setToolTip(
                f"{APP_NAME}\n"
                f"↓ {format_rate(rate.download_bps)}   "
                f"↑ {format_rate(rate.upload_bps)}\n"
                f"Total down: {format_bytes(rate.total_recv)}\n"
                f"Total up:   {format_bytes(rate.total_sent)}"
            )
        except Exception:
            log.exception("Tick failed (will keep running)")

    # ------------------------------ Theme -----------------------------------

    def _apply_theme(self) -> None:
        mode = MODES.get(self._settings.theme_mode, MODES["dark"])
        colors = COLOR_THEMES.get(self._settings.color_theme, COLOR_THEMES["ocean"])
        app = QApplication.instance()
        if app:
            app.setStyleSheet(generate_qss(mode, colors))
        self.graph.apply_theme(mode, colors)

    # ------------------------------ Settings --------------------------------

    def _open_settings(self) -> None:
        dlg = SettingsDialog(self._settings, parent=self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            previous_iface = self._settings.interface
            self._settings = dlg.apply_to(self._settings)
            self._store.save(self._settings)
            self._timer.setInterval(self._settings.update_interval_ms)
            self.graph.set_history_seconds(self._settings.history_seconds)
            self._apply_opacity()
            self._apply_window_flags()
            self._apply_theme()
            if self._settings.interface != previous_iface:
                self._initialise_sampler(self._settings.interface)

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
        self._save_window_state()
        try:
            self._timer.stop()
        except Exception:
            pass
        for t in (self._update_thread, self._download_thread):
            try:
                if t is not None and t.isRunning():
                    t.quit()
                    t.wait(1500)
            except Exception:
                pass
        self.close()
        QApplication.instance().quit()

    # ------------------------------- Updates --------------------------------

    def _check_for_updates(self, silent: bool) -> None:
        if self._update_worker is not None:
            return
        log.info("Checking for updates (silent=%s)", silent)
        worker = UpdateCheckWorker()
        worker.finished.connect(
            lambda info, err: self._on_update_check_done(info, err, silent)
        )
        thread = run_in_thread(worker)
        thread.finished.connect(self._release_update_refs)
        self._update_worker = worker
        self._update_thread = thread

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
            except Exception as exc:
                QMessageBox.warning(self, "Could not launch installer", str(exc))
                return
            self._quit_application()

        worker.progress.connect(on_progress)
        worker.finished.connect(on_finished)
        progress.canceled.connect(lambda: None)

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
                ok = self.restoreGeometry(self._settings.window_geometry)
                log.info("restoreGeometry -> %s", ok)
            except Exception:
                log.exception("restoreGeometry failed")
        if self._settings.window_state:
            try:
                self.restoreState(self._settings.window_state)
            except Exception:
                log.exception("restoreState failed")

    def _save_window_state(self) -> None:
        # Don't save if the window is hidden — its geometry is then invalid.
        if not self.isVisible():
            return
        try:
            self._settings.window_geometry = bytes(self.saveGeometry())
            self._settings.window_state = bytes(self.saveState())
            self._store.save(self._settings)
        except Exception:
            log.exception("Failed to save window state")

    # ----------------------------- Move / resize ----------------------------

    def moveEvent(self, event: QMoveEvent) -> None:
        super().moveEvent(event)
        # Debounced save so we don't write QSettings on every pixel of a drag.
        self._geom_save_timer.start()

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        self._geom_save_timer.start()

    # ----------------------------- Close handling ---------------------------

    def closeEvent(self, event: QCloseEvent) -> None:
        self._save_window_state()
        if self._force_quit or not self._settings.minimize_to_tray_on_close:
            event.accept()
            return
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
    app.setQuitOnLastWindowClosed(False)
    app.setWindowIcon(load_app_icon())
    # Save state once more on normal quit (catches signal-based exits too).
    return app
