@echo off
REM Optional TagOS Manager entry: opens the running launcher's Settings window.
set "LAUNCHER_DIR=C:\path\to\TagOS-Launcher"

cd /d "%LAUNCHER_DIR%"
"%LAUNCHER_DIR%\.venv\Scripts\python.exe" -m tagos_launcher --settings
