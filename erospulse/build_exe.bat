@echo off
REM ============================================================
REM  build_exe.bat
REM  Builds ErosPulse.exe from source, on Windows.
REM
REM  Requirements: Python 3.10+ installed and available as
REM  "python" on PATH. Nothing else needs to be pre-installed:
REM  this script installs PyInstaller itself, and points it at
REM  the vendor/ folder already bundled with the project so that
REM  requests/urllib3/etc. get packaged into the .exe without any
REM  extra "pip install" of your own.
REM
REM  Run this file from the project root (double-click it, or
REM  run it from a command prompt opened in this folder).
REM ============================================================

setlocal
cd /d "%~dp0"

echo.
echo === Installing PyInstaller ===
python -m pip install --upgrade pyinstaller

REM Optional: bleak = direct Bluetooth mode. A failure here is not fatal
REM (the executable will simply not offer direct Bluetooth).
python -m pip install --upgrade bleak
if errorlevel 1 (
    echo.
    echo WARNING: could not install bleak - the executable will be built
    echo WITHOUT the direct Bluetooth mode ^(Wi-Fi mode is unaffected^).
)
if errorlevel 1 (
    echo.
    echo Failed to install PyInstaller. Make sure Python and pip are
    echo installed and available as "python" on PATH, then try again.
    pause
    exit /b 1
)

echo.
echo === Building ErosPulse.exe ===
set PYTHONPATH=%~dp0vendor;%PYTHONPATH%
python -m PyInstaller ErosPulse.spec --noconfirm
if errorlevel 1 (
    echo.
    echo Build failed - see the errors above.
    pause
    exit /b 1
)

echo.
echo ============================================================
echo  Done. Your executable is at: dist\ErosPulse.exe
echo ============================================================
pause
