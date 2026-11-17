@echo off
cd /d "%~dp0"

where python >nul 2>nul
if errorlevel 1 (
    echo Python not found. Install it from https://www.python.org/downloads/
    echo and tick "Add python.exe to PATH" during installation.
    pause
    exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
    echo First run - installing required libraries, this may take a moment...
    python -m venv .venv || goto :error
)
".venv\Scripts\python.exe" -m pip install -q --disable-pip-version-check -r requirements.txt || goto :error

start "" ".venv\Scripts\pythonw.exe" app.py
exit /b 0

:error
echo Installation failed. Delete the .venv folder and try again.
pause
exit /b 1
