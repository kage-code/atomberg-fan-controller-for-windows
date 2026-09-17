@echo off
cd /d "%~dp0"

where python >nul 2>nul
if errorlevel 1 (
    echo Python was not found on PATH. Install it from https://python.org
    echo and make sure "Add python.exe to PATH" is checked during setup.
    pause
    exit /b 1
)

python -c "import requests" >nul 2>nul
if errorlevel 1 (
    echo Installing dependencies...
    python -m pip install -r requirements.txt
)

echo Starting Atomberg Fan Control...
python fan_control.py