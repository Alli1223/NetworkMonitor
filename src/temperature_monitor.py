"""CPU + motherboard temperatures via LibreHardwareMonitorLib (pythonnet).

GPU temperature is read from NVML in :mod:`src.system_monitor`.  This module
fills the gap Windows does not expose to an unprivileged process: the CPU
package temperature and the motherboard / Super-I/O temperatures (the best
available proxy for "inside the case").

Those sensors require ring-0 access via LHM's kernel driver, which only loads
with administrator rights.  Without elevation the CPU temp reads 0 and the
motherboard sensors do not enumerate — we detect that and report
``needs_admin`` so the UI can offer to relaunch elevated.

Everything is defensive: on a non-Windows host, a missing DLL, or any load
failure we return an "unavailable" sample rather than raising.  Sensor reads
happen on a background QThread because Open()/Update() touch hardware.
"""

from __future__ import annotations

import ctypes
import logging
import os
import sys
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from PyQt6.QtCore import QThread, pyqtSignal

log = logging.getLogger(__name__)


def is_admin() -> bool:
    """True when the current process has Windows administrator rights."""
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())  # type: ignore[attr-defined]
    except Exception:
        return False


def _vendor_path() -> str:
    """Locate the bundled LHM DLLs in both source and PyInstaller runs."""
    base = getattr(sys, "_MEIPASS", None)
    if base:
        return os.path.join(base, "vendor", "lhm")
    here = os.path.dirname(os.path.abspath(__file__))
    return os.path.normpath(os.path.join(here, "..", "vendor", "lhm"))


@dataclass
class TempSample:
    """A temperature snapshot.  All temps in degrees Celsius."""

    available: bool = False          # LHM loaded and hardware opened
    is_admin: bool = False
    needs_admin: bool = False        # readings are gated behind elevation
    cpu_c: Optional[float] = None
    mobo_c: Optional[float] = None   # representative motherboard / case temp
    cpu_label: str = "CPU"
    mobo_label: str = "Motherboard"
    extras: Dict[str, float] = field(default_factory=dict)  # all other temps
    error: Optional[str] = None


# Substrings used to recognise a representative motherboard / case sensor,
# in order of preference.
_MOBO_HINTS = ("motherboard", "mainboard", "system", "case", "board")
# Substrings that identify the CPU package/die temperature.
_CPU_HINTS = ("tctl", "tdie", "package", "cpu")


class TemperatureReader:
    """Loads LibreHardwareMonitorLib and reads CPU/motherboard temps.

    Construct it on the thread that will use it (pythonnet objects prefer to
    stay on one thread).  Call :meth:`read` repeatedly, then :meth:`close`.
    """

    def __init__(self) -> None:
        self._ok = False
        self._error: Optional[str] = None
        self._computer = None
        self._SensorType = None
        self._HardwareType = None
        self._load()

    # ------------------------------------------------------------------ #
    #  Load / open                                                        #
    # ------------------------------------------------------------------ #

    def _load(self) -> None:
        if sys.platform != "win32":
            self._error = "Temperatures require Windows"
            return
        vendor = _vendor_path()
        dll = os.path.join(vendor, "LibreHardwareMonitorLib.dll")
        if not os.path.exists(dll):
            self._error = "LibreHardwareMonitorLib.dll not bundled"
            log.warning("LHM DLL missing at %s", dll)
            return
        try:
            if vendor not in sys.path:
                sys.path.append(vendor)
            import clr  # type: ignore

            clr.AddReference("HidSharp")
            clr.AddReference("LibreHardwareMonitorLib")
            from LibreHardwareMonitor.Hardware import (  # type: ignore
                Computer, HardwareType, SensorType,
            )

            self._HardwareType = HardwareType
            self._SensorType = SensorType
            computer = Computer()
            computer.IsCpuEnabled = True
            computer.IsGpuEnabled = False        # GPU temp comes from NVML
            computer.IsMotherboardEnabled = True
            computer.Open()
            self._computer = computer
            self._ok = True
            log.info("LibreHardwareMonitor opened (admin=%s)", is_admin())
        except Exception as exc:  # pragma: no cover - hardware/CLR dependent
            self._error = f"{type(exc).__name__}: {exc}"
            log.warning("Failed to load LibreHardwareMonitor: %s", self._error)

    # ------------------------------------------------------------------ #
    #  Read                                                               #
    # ------------------------------------------------------------------ #

    def _iter_temp_sensors(self, hw) -> List[Tuple[str, float]]:
        """Return (name, value) for every temperature sensor on *hw*."""
        out: List[Tuple[str, float]] = []
        try:
            hw.Update()
        except Exception:
            log.debug("hw.Update failed for %s", getattr(hw, "Name", "?"))
        for s in hw.Sensors:
            if s.SensorType == self._SensorType.Temperature:
                val = s.Value
                if val is not None:
                    out.append((str(s.Name), float(val)))
        for sub in hw.SubHardware:
            out.extend(self._iter_temp_sensors(sub))
        return out

    @staticmethod
    def _pick(named: List[Tuple[str, float]], hints) -> Optional[Tuple[str, float]]:
        """Pick the first sensor whose name matches a hint, in hint order."""
        for hint in hints:
            for name, val in named:
                if hint in name.lower():
                    return name, val
        return None

    def read(self) -> TempSample:
        admin = is_admin()
        if not self._ok or self._computer is None:
            return TempSample(available=False, is_admin=admin, error=self._error)

        cpu_named: List[Tuple[str, float]] = []
        mobo_named: List[Tuple[str, float]] = []
        try:
            for hw in self._computer.Hardware:
                htype = str(hw.HardwareType)
                temps = self._iter_temp_sensors(hw)
                if htype == "Cpu":
                    cpu_named.extend(temps)
                elif htype == "Motherboard":
                    mobo_named.extend(temps)
        except Exception as exc:
            return TempSample(available=False, is_admin=admin,
                              error=f"{type(exc).__name__}: {exc}")

        extras: Dict[str, float] = {}
        for name, val in cpu_named + mobo_named:
            extras[name] = round(val, 1)

        cpu_pick = self._pick(cpu_named, _CPU_HINTS) or (cpu_named[0] if cpu_named else None)
        mobo_pick = self._pick(mobo_named, _MOBO_HINTS) or (mobo_named[0] if mobo_named else None)

        cpu_c = cpu_pick[1] if cpu_pick else None
        mobo_c = mobo_pick[1] if mobo_pick else None

        # Without admin the CPU sensor reads exactly 0.0 and the motherboard
        # Super-I/O sensors do not enumerate at all.  Treat a 0.0 CPU temp as
        # "unavailable" so we never show a misleading 0 C.
        if cpu_c is not None and cpu_c <= 0.0:
            cpu_c = None
        needs_admin = (not admin) and (cpu_c is None or mobo_c is None)

        return TempSample(
            available=True,
            is_admin=admin,
            needs_admin=needs_admin,
            cpu_c=cpu_c,
            mobo_c=mobo_c,
            cpu_label=cpu_pick[0] if cpu_pick else "CPU",
            mobo_label=mobo_pick[0] if mobo_pick else "Motherboard",
            extras=extras,
        )

    def close(self) -> None:
        if self._computer is not None:
            try:
                self._computer.Close()
            except Exception:
                pass
            self._computer = None
        self._ok = False


class TemperatureThread(QThread):
    """Polls :class:`TemperatureReader` and emits a :class:`TempSample`.

    The reader (and thus the LHM kernel driver) is created inside :meth:`run`
    so all CLR access stays on this thread.
    """

    result = pyqtSignal(object)  # TempSample

    def __init__(self, interval_s: float = 2.0, parent=None):
        super().__init__(parent)
        self._interval = interval_s
        self._stop = False

    def run(self) -> None:
        reader = TemperatureReader()
        try:
            while not self._stop:
                try:
                    sample = reader.read()
                except Exception:
                    log.exception("Temperature read failed")
                    sample = TempSample(available=False, error="read failed")
                self.result.emit(sample)
                # Sleep in small slices so stop() is responsive.
                waited = 0.0
                while waited < self._interval and not self._stop:
                    self.msleep(100)
                    waited += 0.1
        finally:
            reader.close()

    def stop(self) -> None:
        self._stop = True
        self.wait(4000)
