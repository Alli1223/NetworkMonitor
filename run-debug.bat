@echo off
REM Run Network Monitor in DEBUG mode.
REM
REM This launches with python.exe (not pythonw.exe) so a console window stays
REM open and any stack traces / Qt warnings are visible. Use this when the app
REM crashes silently — the error will print here and also be written to:
REM
REM   %APPDATA%\NetworkMonitor\networkmonitor.log
REM
REM Press Ctrl+C in this window (or close the app) to stop.

setlocal
cd /d "%~dp0"

set "VENV_DIR=.venv"
set "VENV_PY=%VENV_DIR%\Scripts\python.exe"

if not exist "%VENV_PY%" (
    echo Creating virtual environment in %VENV_DIR% ...
    where py >nul 2>&1
    if %ERRORLEVEL% == 0 (
        py -3 -m venv "%VENV_DIR%"
    ) else (
        python -m venv "%VENV_DIR%"
    )
    if errorlevel 1 (
        echo Failed to create virtual environment. Make sure Python 3.10+ is installed.
        pause
        exit /b 1
    )

    echo Installing dependencies ...
    "%VENV_PY%" -m pip install --upgrade pip
    "%VENV_PY%" -m pip install -r requirements.txt
    if errorlevel 1 (
        echo Failed to install dependencies.
        pause
        exit /b 1
    )
)

echo.
echo === Launching Network Monitor in DEBUG mode ===
echo Log file: %APPDATA%\NetworkMonitor\networkmonitor.log
echo.

"%VENV_PY%" -u "%~dp0main.py" --debug
set "RC=%ERRORLEVEL%"
echo.
echo Network Monitor exited with code %RC%.
pause
endlocal
