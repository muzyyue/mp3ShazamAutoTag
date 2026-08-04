@echo off
rem ============================================================
rem  Imusic launcher - virtual environment
rem  Double-click  : GUI runs in BACKGROUND (no console window)
rem  With args     : runs FOREGROUND CLI with visible output
rem    e.g. start.bat --gui false --help
rem  Uses .venv (uv).
rem ============================================================
setlocal
cd /d "%~dp0"

set "PYTHONW=.venv\Scripts\pythonw.exe"
set "PYTHON=.venv\Scripts\python.exe"
if not exist "%PYTHON%" (
    echo [ERROR] Virtual environment .venv not found. Create it first:
    echo   uv venv
    pause
    exit /b 1
)

if "%*"=="" (
    rem --- Background GUI mode: no console window, launcher returns ---
    start "" "%PYTHONW%" main.py
) else (
    rem --- Foreground CLI mode: keep console for output ---
    "%PYTHON%" main.py %*
)
endlocal
