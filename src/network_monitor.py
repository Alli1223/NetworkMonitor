"""Cross-platform network interface monitoring.

Wraps psutil to:
- enumerate network interfaces (with friendly names where possible)
- sample bytes sent/received per second on a chosen interface
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Dict, List, Optional

import psutil


@dataclass
class InterfaceSnapshot:
    """A single point-in-time sample of an interface's counters."""

    name: str
    timestamp: float
    bytes_sent: int
    bytes_recv: int
    packets_sent: int
    packets_recv: int


@dataclass
class InterfaceRate:
    """Computed per-second rate between two snapshots."""

    name: str
    timestamp: float
    upload_bps: float  # bytes per second
    download_bps: float  # bytes per second
    total_sent: int  # cumulative bytes sent since OS boot
    total_recv: int  # cumulative bytes recv since OS boot


@dataclass
class InterfaceInfo:
    """Display-friendly info about an interface."""

    name: str  # the key psutil uses (e.g. "eth0", "Ethernet")
    display_name: str
    is_up: bool
    speed_mbps: int  # 0 if unknown
    addresses: List[str]


def list_interfaces() -> List[InterfaceInfo]:
    """Return all known interfaces, sorted with active ones first."""
    stats = psutil.net_if_stats()
    addrs = psutil.net_if_addrs()
    result: List[InterfaceInfo] = []
    for name, stat in stats.items():
        ip_list: List[str] = []
        for addr in addrs.get(name, []):
            # Family values differ slightly on Windows vs Linux; filter by string.
            family_name = getattr(addr.family, "name", str(addr.family))
            if "AF_INET" in family_name and addr.address:
                ip_list.append(addr.address)
        result.append(
            InterfaceInfo(
                name=name,
                display_name=name,
                is_up=stat.isup,
                speed_mbps=stat.speed or 0,
                addresses=ip_list,
            )
        )
    # Sort: up interfaces first, then those with IPs, then alphabetic
    result.sort(key=lambda i: (not i.is_up, not i.addresses, i.name.lower()))
    return result


def _snapshot(interface: str) -> Optional[InterfaceSnapshot]:
    counters: Dict[str, psutil._common.snetio] = psutil.net_io_counters(pernic=True)
    c = counters.get(interface)
    if c is None:
        return None
    return InterfaceSnapshot(
        name=interface,
        timestamp=time.monotonic(),
        bytes_sent=c.bytes_sent,
        bytes_recv=c.bytes_recv,
        packets_sent=c.packets_sent,
        packets_recv=c.packets_recv,
    )


class NetworkSampler:
    """Stateful sampler that produces a rate each time it is polled.

    Usage:
        sampler = NetworkSampler("eth0")
        rate = sampler.poll()  # first call returns zeros (baseline)
        ...
        rate = sampler.poll()  # subsequent calls return real rates
    """

    def __init__(self, interface: str):
        self._interface = interface
        self._previous: Optional[InterfaceSnapshot] = None

    @property
    def interface(self) -> str:
        return self._interface

    def set_interface(self, interface: str) -> None:
        """Switch to a different interface. Resets the baseline."""
        if interface != self._interface:
            self._interface = interface
            self._previous = None

    def poll(self) -> Optional[InterfaceRate]:
        """Take a sample and return the rate since the previous sample.

        Returns None if the interface cannot be read. Returns a zeroed
        InterfaceRate on the first poll (no baseline yet).
        """
        current = _snapshot(self._interface)
        if current is None:
            self._previous = None
            return None
        previous = self._previous
        self._previous = current
        if previous is None:
            return InterfaceRate(
                name=self._interface,
                timestamp=current.timestamp,
                upload_bps=0.0,
                download_bps=0.0,
                total_sent=current.bytes_sent,
                total_recv=current.bytes_recv,
            )
        dt = max(current.timestamp - previous.timestamp, 1e-6)
        # Counters can reset (e.g. interface bounced); clamp negatives to zero.
        d_sent = max(current.bytes_sent - previous.bytes_sent, 0)
        d_recv = max(current.bytes_recv - previous.bytes_recv, 0)
        return InterfaceRate(
            name=self._interface,
            timestamp=current.timestamp,
            upload_bps=d_sent / dt,
            download_bps=d_recv / dt,
            total_sent=current.bytes_sent,
            total_recv=current.bytes_recv,
        )


def format_rate(bytes_per_second: float) -> str:
    """Human-friendly rate string. Uses bits for sub-MB and bytes for larger."""
    return format_bytes(bytes_per_second) + "/s"


def format_bytes(num_bytes: float) -> str:
    """Human-friendly byte count: 'B', 'KB', 'MB', 'GB', 'TB'."""
    n = float(num_bytes)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(n) < 1024.0:
            if unit == "B":
                return f"{n:.0f} {unit}"
            return f"{n:.2f} {unit}"
        n /= 1024.0
    return f"{n:.2f} PB"
