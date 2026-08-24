@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title Local Transcriber - Windows Setup

echo ============================================================
echo              LOCAL TRANSCRIBER - WINDOWS SETUP
echo ============================================================
echo.
echo This will create a private Python environment and install all
echo dependencies required by Local Transcriber.
echo.

if not exist .venv\Scripts\python.exe (
  echo [1/4] Creating the Python environment...
  py -3.12 -m venv .venv >nul 2>&1
  if errorlevel 1 py -3 -m venv .venv >nul 2>&1
  if errorlevel 1 python -m venv .venv >nul 2>&1
  if not exist .venv\Scripts\python.exe goto :python_error
) else (
  echo [1/4] Existing Python environment found.
)

echo [2/4] Updating the package installer...
.venv\Scripts\python.exe -m pip install --upgrade pip
if errorlevel 1 goto :install_error

echo [3/4] Installing Local Transcriber dependencies...
.venv\Scripts\python.exe -m pip install -r requirements.txt
if errorlevel 1 goto :install_error

echo [4/4] Checking the installation...
.venv\Scripts\python.exe -c "import fastapi, uvicorn, faster_whisper; print('Python transcription packages: READY')"
if errorlevel 1 goto :verify_error

where ffmpeg >nul 2>&1
if errorlevel 1 goto :ffmpeg_warning
where ffprobe >nul 2>&1
if errorlevel 1 goto :ffmpeg_warning

echo FFmpeg and FFprobe: READY
echo.
echo ============================================================
echo SETUP COMPLETE
echo You can now double-click start-windows.bat
echo ============================================================
echo.
pause
exit /b 0

:ffmpeg_warning
echo.
echo ============================================================
echo PYTHON SETUP COMPLETE - FFMPEG STILL NEEDED
echo Install it with: winget install -e --id Gyan.FFmpeg
echo Then close this window and run this installer again.
echo ============================================================
echo.
pause
exit /b 2

:python_error
echo.
echo SETUP FAILED: Python was not found.
echo Install 64-bit Python 3.12 from https://python.org/downloads/windows/
echo Then restart this installer.
goto :failed

:install_error
echo.
echo SETUP FAILED while downloading or installing Python packages.
echo Check the internet connection and the error shown above.
goto :failed

:verify_error
echo.
echo SETUP FAILED: the transcription packages could not be imported.
echo Review the error above or send it to the tool administrator.

:failed
echo.
pause
exit /b 1
