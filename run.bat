@echo off
REM Launch Network Monitor from source on Windows.
REM
REM On first run it creates a .venv, installs requirements, and starts the app.
REM On subsequent runs it just activates the venv and starts the app.
REM Uses pythonw.exe so no console window stays open behind the app.

setlocal
cd /d "%~dp0"

set "VENV_DIR=.venv"
set "VENV_PY=%VENV_DIR%\Scripts\python.exe"
set "VENV_PYW=%VENV_DIR%\Scripts\pythonw.exe"

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

REM Launch with pythonw so no console window stays open.
start "" "%VENV_PYW%" "%~dp0main.py"
endlocal
