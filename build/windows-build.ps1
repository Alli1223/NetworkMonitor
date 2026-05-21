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

# Ensure an .ico exists so the exe and the installer have a Windows icon.
$ico = "$root\assets\icon.ico"
if (-not (Test-Path $ico)) {
    Write-Host ">> assets\icon.ico not found; converting from icon.svg"
    python -m pip install pillow cairosvg
    python "$root\build\svg_to_ico.py"
    if (-not (Test-Path $ico)) {
        throw "Icon conversion failed; assets\icon.ico still missing."
    }
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
