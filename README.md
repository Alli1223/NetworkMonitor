# Network Monitor

A lightweight cross-platform network traffic monitor for Windows and Linux. Pick an interface, watch upload and download rates update every second on a clean dark graph, leave it tucked in the corner of your desktop, and let it auto-update from GitHub Releases.

## Features

- Live upload/download graph (updates every second by default)
- Pick any network interface; remembers your choice
- Compact, dark, modern UI designed to live in a desktop corner
- System tray icon with show/hide/quit + tooltip showing current rates
- Optional "minimize to tray on close" and "start minimized"
- Settings persisted via `QSettings` (registry on Windows, `~/.config` on Linux)
- Auto-update by polling the GitHub Releases API; prompts before installing
- Windows installer (Inno Setup) installs to `Program Files`
- Linux AppImage build for portable single-file distribution
- GitHub Actions workflow that builds Windows + Linux artifacts on tag push and publishes a release

## Running from source

```bash
python -m venv .venv
# Windows:  .venv\Scripts\activate
# Linux:    source .venv/bin/activate
pip install -r requirements.txt
python main.py
```

Requires Python 3.10+.

## Installing on Windows

Download `NetworkMonitor-Setup.exe` from the latest GitHub Release and run it. The installer puts the app under `C:\Program Files\NetworkMonitor`, registers an Add/Remove Programs entry, and offers to create a desktop shortcut and a Start-with-Windows shortcut.

## Installing on Linux

Download `NetworkMonitor-<version>-x86_64.AppImage` from the latest GitHub Release, mark it executable, and run it:

```bash
chmod +x NetworkMonitor-*-x86_64.AppImage
./NetworkMonitor-*-x86_64.AppImage
```

## Auto-update

On startup (if enabled in Settings) and on demand from the tray menu, the app fetches the latest release from `https://github.com/<owner>/<repo>/releases/latest`. If the tag is newer than the running version it offers to download the platform-appropriate asset and launch the installer (Windows) or AppImage (Linux). The repo it watches is configured in `src/version.py` as `GITHUB_REPO`.

## Cutting a new release

The full release pipeline is automated by `.github/workflows/release.yml`. To ship a new version:

1. Update `__version__` in `src/version.py` (or let the build scripts overwrite it from the tag).
2. Commit and push.
3. Tag with a `v`-prefixed semver and push the tag:

   ```bash
   git tag v0.2.0
   git push origin v0.2.0
   ```

4. GitHub Actions will build the Windows installer and Linux AppImage, then publish them as a new GitHub Release. Existing users will be prompted to update on their next launch.

You can also trigger the workflow manually from the Actions tab using `workflow_dispatch` and providing a version string.

## Building installers locally

### Windows

Requires [Inno Setup 6](https://jrsoftware.org/isinfo.php) installed at its default location.

```powershell
.\build\windows-build.ps1 -Version 0.1.0
# -> installer_output\NetworkMonitor-Setup.exe
```

### Linux

```bash
chmod +x build/linux-build.sh
./build/linux-build.sh 0.1.0
# -> installer_output/NetworkMonitor-0.1.0-x86_64.AppImage
```

## Project layout

```
main.py                  # Entry point (also used by PyInstaller)
NetworkMonitor.spec      # PyInstaller spec (Windows + Linux)
requirements.txt         # Runtime deps
requirements-build.txt   # Build deps (adds PyInstaller)
src/
  version.py             # __version__, APP_NAME, GITHUB_REPO
  network_monitor.py     # psutil-based sampling backend
  settings.py            # QSettings wrapper
  graph_widget.py        # pyqtgraph live graph
  main_window.py         # MainWindow + tray + dialogs
  style.py               # Dark QSS theme
  updater.py             # GitHub Releases auto-updater
assets/icon.svg          # App + tray icon
installer/windows.iss    # Inno Setup script
build/windows-build.ps1  # Local Windows build script
build/linux-build.sh     # Local Linux AppImage build script
.github/workflows/release.yml  # CI/CD on tag push
```

## Configuration

Settings are stored under:

- **Windows:** `HKEY_CURRENT_USER\Software\NetworkMonitor\NetworkMonitor`
- **Linux:** `~/.config/NetworkMonitor/NetworkMonitor.conf`

Editable from the Settings dialog: graph history length, update interval, start-minimized, minimize-to-tray-on-close, and check-for-updates-on-startup.

## Notes

- The GitHub repo the updater watches is set by `GITHUB_REPO` in `src/version.py`. Update it to match your fork before publishing.
- The Windows installer ID (`AppId` in `installer/windows.iss`) is what Windows uses to identify upgrades vs. fresh installs. Keep it stable across releases so updates replace the previous install in place.
