# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for Network Monitor.

Used on both Windows and Linux; on Windows it produces a windowed exe with
no console, on Linux it produces a single executable suitable for bundling
into an AppImage.
"""

import glob
import os
import sys

block_cipher = None
here = os.path.abspath(os.path.dirname(SPEC))  # noqa: F821  (SPEC injected by PyInstaller)

datas = [
    (os.path.join(here, "assets", "icon.svg"), "assets"),
]
binaries = []
hiddenimports = ["pynvml"]

# Windows-only: bundle the LibreHardwareMonitor DLLs (CPU/motherboard temps)
# and the pythonnet / clr_loader runtime needed to load them.
if sys.platform.startswith("win"):
    for dll in glob.glob(os.path.join(here, "vendor", "lhm", "*.dll")):
        datas.append((dll, os.path.join("vendor", "lhm")))
    from PyInstaller.utils.hooks import collect_all
    for pkg in ("pythonnet", "clr_loader"):
        pkg_datas, pkg_binaries, pkg_hidden = collect_all(pkg)
        datas += pkg_datas
        binaries += pkg_binaries
        hiddenimports += pkg_hidden

a = Analysis(
    [os.path.join(here, "main.py")],
    pathex=[here],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

icon_file = None
if sys.platform.startswith("win"):
    candidate = os.path.join(here, "assets", "icon.ico")
    if os.path.exists(candidate):
        icon_file = candidate

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="NetworkMonitor",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    runtime_tmpdir=None,
    console=False,            # windowed app, no console on Windows
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=icon_file,
)
