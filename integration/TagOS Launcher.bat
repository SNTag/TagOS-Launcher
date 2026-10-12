@echo off
REM TagOS Manager entry for TagOS Launcher.
REM Copy this file and "TagOS Launcher.bat.yaml" into your TagOS Manager
REM scripts folder, then set LAUNCHER_DIR to where you cloned TagOS-Launcher.
REM In TagOS Manager, tick "Persistent" and "Run on startup" on its card.
set "LAUNCHER_DIR=C:\path\to\TagOS-Launcher"

call "%LAUNCHER_DIR%\run.bat" --console
