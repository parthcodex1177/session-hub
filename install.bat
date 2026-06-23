@echo off
:: Session Hub installer for Windows
:: Requirements: Python 3.10+, Edge WebView2 Runtime (ships with Windows 10/11)
setlocal enabledelayedexpansion

set "DIR=%~dp0"
set "VENV=%DIR%.venv"

echo Session Hub — Windows setup
echo.

:: Check Python
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python not found. Install Python 3.10+ from https://python.org
    pause & exit /b 1
)

:: Create venv if missing
if not exist "%VENV%\Scripts\python.exe" (
    echo Creating virtual environment...
    python -m venv "%VENV%"
    if errorlevel 1 ( echo Failed to create venv & pause & exit /b 1 )
    echo Installing dependencies...
    "%VENV%\Scripts\pip" install -q -e "%DIR%"
    if errorlevel 1 ( echo Failed to install dependencies & pause & exit /b 1 )
)

:: Create a desktop shortcut
set "SHORTCUT=%USERPROFILE%\Desktop\Session Hub.lnk"
set "TARGET=%VENV%\Scripts\session-hub-app.exe"
powershell -NoProfile -Command ^
  "$ws = New-Object -ComObject WScript.Shell; $s = $ws.CreateShortcut('%SHORTCUT%'); $s.TargetPath = '%TARGET%'; $s.WorkingDirectory = '%DIR%'; $s.Description = 'Session Hub — AI session history'; $s.Save()" ^
  2>nul && echo Created desktop shortcut: %SHORTCUT% || echo Note: Could not create shortcut (optional)

echo.
echo Done. Run Session Hub:
echo   Double-click the Desktop shortcut, or run:
echo   %VENV%\Scripts\session-hub-app
echo.
pause
