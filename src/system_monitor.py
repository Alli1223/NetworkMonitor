"""System resource sampling: CPU, RAM, disk I/O, and GPU (NVIDIA via NVML).

CPU / RAM / disk come from psutil (no admin needed).  GPU utilisation,
memory and temperature come from NVML (``nvidia-ml-py``) when an NVIDIA GPU
is present — also without admin.  Everything degrades gracefully: a missing
GPU just yields an "unavailable" sample rather than raising.

Temperatures that genuinely require ring-0 access (CPU package, motherboard)
are handled separately in :mod:`src.temperature_monitor`.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import List, Optional

import psutil

log = logging.getLogger(__name__)

# NVML is optional and only meaningful on NVIDIA systems.
try:
    import pynvml  # provided by the ``nvidia-ml-py`` package
    _NVML_IMPORTED = True
except Exception:  # pragma: no cover - import guard
    pynvml = None  # type: ignore
    _NVML_IMPORTED = False


@dataclass
class GpuSample:
    """A single GPU reading.  ``available`` is False when no GPU/NVML."""

    available: bool = False
    name: str = ""
    util_percent: float = 0.0
    mem_used: float = 0.0   # bytes
    mem_total: float = 0.0  # bytes
    temp_c: Optional[float] = None

    @property
    def mem_percent(self) -> float:
        return (self.mem_used / self.mem_total * 100.0) if self.mem_total else 0.0


@dataclass
class SystemSample:
    """A snapshot of system resource usage at one tick."""

    cpu_percent: float = 0.0
    per_core: List[float] = field(default_factory=list)
    ram_used: float = 0.0    # bytes
    ram_total: float = 0.0   # bytes
    ram_percent: float = 0.0
    disk_read_bps: float = 0.0
    disk_write_bps: float = 0.0
    gpu: GpuSample = field(default_factory=GpuSample)

    @property
    def disk_total_bps(self) -> float:
        return self.disk_read_bps + self.disk_write_bps


class SystemSampler:
    """Polls CPU/RAM/disk via psutil and GPU via NVML.

    Call :meth:`poll` once per UI tick.  Disk throughput is derived from the
    delta of the cumulative byte counters divided by real elapsed time, so it
    stays accurate even if the tick interval drifts.
    """

    def __init__(self) -> None:
        # psutil.cpu_percent needs priming — the first call always returns 0.0
        # because it has no previous sample to diff against.
        psutil.cpu_percent(interval=None)
        psutil.cpu_percent(interval=None, percpu=True)

        self._last_disk = self._safe_disk_counters()
        self._last_time = time.monotonic()

        self._nvml_ok = False
        self._gpu_name = ""
        self._gpu_handle = None
        self._init_nvml()

    # ------------------------------------------------------------------ #
    #  GPU / NVML                                                         #
    # ------------------------------------------------------------------ #

    def _init_nvml(self) -> None:
        if not _NVML_IMPORTED:
            log.info("nvidia-ml-py not installed; GPU stats disabled")
            return
        try:
            pynvml.nvmlInit()
            if pynvml.nvmlDeviceGetCount() > 0:
                self._gpu_handle = pynvml.nvmlDeviceGetHandleByIndex(0)
                name = pynvml.nvmlDeviceGetName(self._gpu_handle)
                self._gpu_name = name.decode() if isinstance(name, bytes) else str(name)
                self._nvml_ok = True
                log.info("NVML initialised for GPU: %s", self._gpu_name)
        except Exception:
            log.debug("NVML init failed; GPU stats unavailable", exc_info=True)
            self._nvml_ok = False

    @property
    def gpu_available(self) -> bool:
        return self._nvml_ok

    def _poll_gpu(self) -> GpuSample:
        if not self._nvml_ok:
            return GpuSample(available=False)
        try:
            util = pynvml.nvmlDeviceGetUtilizationRates(self._gpu_handle)
            mem = pynvml.nvmlDeviceGetMemoryInfo(self._gpu_handle)
            try:
                temp = float(pynvml.nvmlDeviceGetTemperature(
                    self._gpu_handle, pynvml.NVML_TEMPERATURE_GPU))
            except Exception:
                temp = None
            return GpuSample(
                available=True,
                name=self._gpu_name,
                util_percent=float(util.gpu),
                mem_used=float(mem.used),
                mem_total=float(mem.total),
                temp_c=temp,
            )
        except Exception:
            log.debug("NVML poll failed", exc_info=True)
            return GpuSample(available=False, name=self._gpu_name)

    # ------------------------------------------------------------------ #
    #  Disk                                                               #
    # ------------------------------------------------------------------ #

    @staticmethod
    def _safe_disk_counters():
        try:
            return psutil.disk_io_counters()
        except Exception:
            return None

    # ------------------------------------------------------------------ #
    #  Poll                                                               #
    # ------------------------------------------------------------------ #

    def poll(self) -> SystemSample:
        now = time.monotonic()
        elapsed = max(now - self._last_time, 1e-3)
        self._last_time = now

        cpu = psutil.cpu_percent(interval=None)
        per_core = psutil.cpu_percent(interval=None, percpu=True)
        vm = psutil.virtual_memory()

        disk = self._safe_disk_counters()
        read_bps = write_bps = 0.0
        if disk and self._last_disk:
            read_bps = max(0.0, (disk.read_bytes - self._last_disk.read_bytes) / elapsed)
            write_bps = max(0.0, (disk.write_bytes - self._last_disk.write_bytes) / elapsed)
        self._last_disk = disk

        return SystemSample(
            cpu_percent=float(cpu),
            per_core=[float(c) for c in per_core],
            ram_used=float(vm.used),
            ram_total=float(vm.total),
            ram_percent=float(vm.percent),
            disk_read_bps=read_bps,
            disk_write_bps=write_bps,
            gpu=self._poll_gpu(),
        )

    def close(self) -> None:
        if self._nvml_ok:
            try:
                pynvml.nvmlShutdown()
            except Exception:
                pass
            self._nvml_ok = False
