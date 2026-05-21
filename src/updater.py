"""GitHub Releases auto-updater.

Checks the latest published release from a GitHub repo and, when newer,
downloads the platform-appropriate asset and launches it. On Windows we
expect an `.exe` installer (Inno Setup); on Linux we expect an `.AppImage`.
"""

from __future__ import annotations

import os
import platform
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from typing import List, Optional

import requests
from packaging.version import InvalidVersion, Version
from PyQt6.QtCore import QObject, QThread, pyqtSignal

from .version import GITHUB_REPO, __version__


@dataclass
class ReleaseAsset:
    name: str
    download_url: str
    size: int


@dataclass
class ReleaseInfo:
    tag: str
    version: Version
    name: str
    body: str
    html_url: str
    assets: List[ReleaseAsset]

    def pick_asset(self) -> Optional[ReleaseAsset]:
        """Return the asset that matches the current platform."""
        system = platform.system().lower()
        if system == "windows":
            # Prefer the installer; fall back to a portable zip.
            preferred_suffixes = ("-setup.exe", "setup.exe", ".exe")
            for suffix in preferred_suffixes:
                for asset in self.assets:
                    if asset.name.lower().endswith(suffix):
                        return asset
        elif system == "linux":
            for asset in self.assets:
                if asset.name.lower().endswith(".appimage"):
                    return asset
        return None


def _parse_version(tag: str) -> Optional[Version]:
    """Tolerate a 'v' prefix on tags like v1.2.3."""
    candidate = tag.lstrip("vV")
    try:
        return Version(candidate)
    except InvalidVersion:
        return None


def fetch_latest_release(repo: str = GITHUB_REPO, timeout: float = 10.0) -> Optional[ReleaseInfo]:
    """Hit GitHub's API for the latest release of `repo` (owner/repo)."""
    url = f"https://api.github.com/repos/{repo}/releases/latest"
    headers = {"Accept": "application/vnd.github+json", "User-Agent": "NetworkMonitor-Updater"}
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    resp = requests.get(url, headers=headers, timeout=timeout)
    if resp.status_code == 404:
        return None  # no releases yet
    resp.raise_for_status()
    data = resp.json()
    tag = data.get("tag_name") or ""
    version = _parse_version(tag)
    if version is None:
        return None
    assets = [
        ReleaseAsset(
            name=a.get("name", ""),
            download_url=a.get("browser_download_url", ""),
            size=int(a.get("size", 0)),
        )
        for a in data.get("assets", [])
    ]
    return ReleaseInfo(
        tag=tag,
        version=version,
        name=data.get("name") or tag,
        body=data.get("body") or "",
        html_url=data.get("html_url") or "",
        assets=assets,
    )


def is_newer(release: ReleaseInfo) -> bool:
    """True if the release is strictly newer than the running version."""
    try:
        current = Version(__version__)
    except InvalidVersion:
        return True
    return release.version > current


def download_asset(asset: ReleaseAsset, dest_dir: Optional[str] = None,
                   progress_cb=None) -> str:
    """Stream the asset to disk and return the file path."""
    dest_dir = dest_dir or tempfile.gettempdir()
    dest_path = os.path.join(dest_dir, asset.name)
    with requests.get(asset.download_url, stream=True, timeout=30) as r:
        r.raise_for_status()
        total = int(r.headers.get("Content-Length", asset.size or 0))
        done = 0
        with open(dest_path, "wb") as f:
            for chunk in r.iter_content(chunk_size=64 * 1024):
                if not chunk:
                    continue
                f.write(chunk)
                done += len(chunk)
                if progress_cb and total > 0:
                    progress_cb(done, total)
    return dest_path


def launch_installer(path: str) -> None:
    """Kick off the downloaded installer/AppImage and exit the current app.

    The caller is responsible for closing the app cleanly after this returns.
    """
    system = platform.system().lower()
    if system == "windows":
        # /SILENT /CLOSEAPPLICATIONS /RESTARTAPPLICATIONS are Inno Setup args.
        # Run the installer as a detached process so it survives our exit.
        subprocess.Popen(
            [path, "/SILENT", "/CLOSEAPPLICATIONS", "/RESTARTAPPLICATIONS"],
            close_fds=True,
        )
    elif system == "linux":
        os.chmod(path, 0o755)
        subprocess.Popen([path], close_fds=True)
    else:
        # macOS or other: just open the file with the system default.
        subprocess.Popen(["xdg-open", path], close_fds=True)


# ---------------------------------------------------------------------------
# Qt threading wrapper so the UI never blocks on network I/O
# ---------------------------------------------------------------------------


class UpdateCheckWorker(QObject):
    """Background worker that fetches release info and emits a signal."""

    finished = pyqtSignal(object, object)  # (release_info or None, error_str or None)

    def __init__(self, repo: str = GITHUB_REPO):
        super().__init__()
        self._repo = repo

    def run(self) -> None:
        try:
            info = fetch_latest_release(self._repo)
            self.finished.emit(info, None)
        except Exception as exc:  # noqa: BLE001 - surface any failure to UI
            self.finished.emit(None, str(exc))


class DownloadWorker(QObject):
    """Background worker that downloads an asset and reports progress."""

    progress = pyqtSignal(int, int)  # (done_bytes, total_bytes)
    finished = pyqtSignal(object, object)  # (path or None, error_str or None)

    def __init__(self, asset: ReleaseAsset):
        super().__init__()
        self._asset = asset

    def run(self) -> None:
        try:
            path = download_asset(self._asset, progress_cb=lambda d, t: self.progress.emit(d, t))
            self.finished.emit(path, None)
        except Exception as exc:  # noqa: BLE001
            self.finished.emit(None, str(exc))


def run_in_thread(worker: QObject) -> QThread:
    """Start `worker.run()` on a fresh QThread.

    The caller MUST keep both `worker` and the returned thread alive (e.g.
    on `self.foo_worker` / `self.foo_thread`) until `thread.finished` fires,
    then release them. Don't connect deleteLater here — that's a common
    source of "QThread: Destroyed while thread is still running" on Windows.
    """
    thread = QThread()
    worker.moveToThread(thread)
    thread.started.connect(worker.run)
    if hasattr(worker, "finished"):
        # When work is done, quit the thread's event loop. The caller is
        # responsible for releasing references on `thread.finished`.
        worker.finished.connect(thread.quit)  # type: ignore[attr-defined]
    thread.start()
    return thread


def running_as_frozen_exe() -> bool:
    """True when running from a PyInstaller bundle."""
    return getattr(sys, "frozen", False)
