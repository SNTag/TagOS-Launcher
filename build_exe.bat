@echo off
REM Build a standalone TagOS Launcher.exe with PyInstaller.
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    python -m venv .venv
    ".venv\Scripts\python.exe" -m pip install --upgrade pip
    ".venv\Scripts\python.exe" -m pip install -r requirements.txt
)

".venv\Scripts\python.exe" -m pip install pyinstaller
REM Build from app.py (absolute import) rather than tagos_launcher\__main__.py,
REM whose relative imports break when PyInstaller runs it as a top-level script.
".venv\Scripts\python.exe" -m PyInstaller ^
    --noconfirm --clean --windowed --onefile ^
    --name "TagOS Launcher" ^
    app.py

echo.
echo Build complete. See dist\TagOS Launcher.exe
endlocal
