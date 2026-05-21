#!/usr/bin/env bash
# Build a portable AppImage for Linux.
#
# Usage:
#   ./build/linux-build.sh 0.1.0
#
# Produces installer_output/NetworkMonitor-x86_64.AppImage

set -euo pipefail

VERSION="${1:-0.1.0}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

echo ">> Setting __version__ to $VERSION"
python - <<PY
import re, pathlib
p = pathlib.Path("src/version.py")
p.write_text(re.sub(r'__version__\s*=\s*".*"', f'__version__ = "$VERSION"', p.read_text()))
PY

echo ">> Installing build deps"
python -m pip install --upgrade pip
python -m pip install -r requirements-build.txt

echo ">> Running PyInstaller"
rm -rf build/NetworkMonitor dist
python -m PyInstaller --noconfirm --clean NetworkMonitor.spec

if [ ! -f "$ROOT/dist/NetworkMonitor" ]; then
    echo "PyInstaller did not produce dist/NetworkMonitor"
    exit 1
fi

echo ">> Assembling AppDir"
APPDIR="$ROOT/build/NetworkMonitor.AppDir"
rm -rf "$APPDIR"
mkdir -p "$APPDIR/usr/bin" "$APPDIR/usr/share/applications" "$APPDIR/usr/share/icons/hicolor/256x256/apps"
cp "$ROOT/dist/NetworkMonitor" "$APPDIR/usr/bin/NetworkMonitor"
chmod +x "$APPDIR/usr/bin/NetworkMonitor"

# Convert SVG to PNG for the AppImage icon (linuxdeploy prefers PNG).
python -m pip install cairosvg pillow
python - <<PY
from cairosvg import svg2png
svg2png(url="$ROOT/assets/icon.svg", write_to="$APPDIR/networkmonitor.png", output_width=256, output_height=256)
PY
cp "$APPDIR/networkmonitor.png" "$APPDIR/usr/share/icons/hicolor/256x256/apps/networkmonitor.png"

cat > "$APPDIR/networkmonitor.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=Network Monitor
Exec=NetworkMonitor
Icon=networkmonitor
Categories=Network;Monitor;Utility;
Terminal=false
StartupNotify=false
EOF
cp "$APPDIR/networkmonitor.desktop" "$APPDIR/usr/share/applications/networkmonitor.desktop"

cat > "$APPDIR/AppRun" <<'EOF'
#!/bin/bash
HERE="$(dirname "$(readlink -f "$0")")"
exec "$HERE/usr/bin/NetworkMonitor" "$@"
EOF
chmod +x "$APPDIR/AppRun"

echo ">> Downloading appimagetool"
TOOL="$ROOT/build/appimagetool-x86_64.AppImage"
if [ ! -f "$TOOL" ]; then
    curl -sSL -o "$TOOL" \
        "https://github.com/AppImage/AppImageKit/releases/download/continuous/appimagetool-x86_64.AppImage"
    chmod +x "$TOOL"
fi

mkdir -p "$ROOT/installer_output"
OUT="$ROOT/installer_output/NetworkMonitor-${VERSION}-x86_64.AppImage"
ARCH=x86_64 "$TOOL" "$APPDIR" "$OUT"

echo ">> Done. AppImage at $OUT"
