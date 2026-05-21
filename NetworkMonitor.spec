# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for Network Monitor.

Used on both Windows and Linux; on Windows it produces a windowed exe with
no console, on Linux it produces a single executable suitable for bundling
into an AppImage.
"""

import os
import sys

block_cipher = None
here = os.path.abspath(os.path.dirname(SPEC))  # noqa: F821  (SPEC injected by PyInstaller)

datas = [
    (os.path.join(here, "assets", "icon.svg"), "assets"),
]

a = Analysis(
    [os.path.join(here, "main.py")],
    pathex=[here],
    binaries=[],
    datas=datas,
    hiddenimports=[],
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
