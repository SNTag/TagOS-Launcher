@echo off
REM Launch TagOS Launcher. Creates a local virtual environment on first run.
REM   run.bat            start in the background (tray only, no console)
REM   run.bat --console  run in this console so output is visible
REM                      (used by TagOS Manager, which shows it in a tab)
REM Any other arguments (--show, --settings, --quit) go to the launcher.
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo Creating virtual environment...
    python -m venv .venv
    if errorlevel 1 (
        echo Failed to create virtual environment. Is Python installed and on PATH?
        pause
        exit /b 1
    )
    echo Installing dependencies...
    ".venv\Scripts\python.exe" -m pip install --upgrade pip
    ".venv\Scripts\python.exe" -m pip install -r requirements.txt
)

if /i "%~1"=="--console" goto console

REM pythonw runs without a console window.
start "" ".venv\Scripts\pythonw.exe" -m tagos_launcher %*
goto end

:console
shift
".venv\Scripts\python.exe" -u -m tagos_launcher %1 %2 %3 %4

:end
endlocal
