# Build script for Windows.
#
# Prereqs: Python 3.10+, Inno Setup 6 installed at the default location, and
# (optionally) an icon.ico converted from assets/icon.svg.
#
# Usage:
#   .\build\windows-build.ps1 -Version 0.1.0

param(
    [string]$Version = "0.1.0"
)

$ErrorActionPreference = "Stop"

$root = Resolve-Path "$PSScriptRoot\.."
Set-Location $root

Write-Host ">> Setting __version__ to $Version"
$versionFile = "$root\src\version.py"
(Get-Content $versionFile) `
    -replace '__version__\s*=\s*".*"', "__version__ = `"$Version`"" `
    | Set-Content $versionFile

Write-Host ">> Installing build deps"
python -m pip install --upgrade pip
python -m pip install -r requirements-build.txt

# Ensure an .ico exists so the exe has a Windows icon.
$ico = "$root\assets\icon.ico"
if (-not (Test-Path $ico)) {
    Write-Host ">> assets/icon.ico not found; trying to convert from icon.svg via Pillow + cairosvg"
    python -m pip install pillow cairosvg
    python - <<'PY'
import os
from cairosvg import svg2png
from PIL import Image
import io
root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
svg = os.path.join(root, 'assets', 'icon.svg')
ico = os.path.join(root, 'assets', 'icon.ico')
png_bytes = svg2png(url=svg, output_width=256, output_height=256)
img = Image.open(io.BytesIO(png_bytes)).convert('RGBA')
sizes = [(16,16),(24,24),(32,32),(48,48),(64,64),(128,128),(256,256)]
img.save(ico, sizes=sizes)
print('Wrote', ico)
PY
}

Write-Host ">> Running PyInstaller"
Remove-Item -Recurse -Force -ErrorAction Ignore "$root\build\NetworkMonitor"
Remove-Item -Recurse -Force -ErrorAction Ignore "$root\dist"
python -m PyInstaller --noconfirm --clean NetworkMonitor.spec

if (-not (Test-Path "$root\dist\NetworkMonitor.exe")) {
    throw "PyInstaller did not produce dist\NetworkMonitor.exe"
}

Write-Host ">> Building installer with Inno Setup"
$iscc = "C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
if (-not (Test-Path $iscc)) {
    $iscc = "C:\Program Files\Inno Setup 6\ISCC.exe"
}
if (-not (Test-Path $iscc)) {
    throw "Could not find ISCC.exe. Install Inno Setup 6 from https://jrsoftware.org/isinfo.php"
}

New-Item -ItemType Directory -Force -Path "$root\installer_output" | Out-Null
& $iscc /DAppVersion=$Version "$root\installer\windows.iss"

Write-Host ">> Done. Installer at $root\installer_output\NetworkMonitor-Setup.exe"
