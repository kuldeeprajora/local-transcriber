@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title Local Transcriber
set "VENV_PYTHON=%CD%\.venv\Scripts\python.exe"

call :check_ready
if errorlevel 1 (
  echo Local Transcriber needs setup or repair.
  echo Starting the safe installer...
  echo.
  call INSTALL-WINDOWS.bat
  if errorlevel 1 (
    echo.
    echo The app was not started because setup is incomplete.
    pause
    exit /b 1
  )
)

echo Starting Local Transcriber at http://localhost:8000/
"%VENV_PYTHON%" run.py
if errorlevel 1 (
  echo.
  echo The server stopped with an error. Run INSTALL-WINDOWS.bat to repair dependencies.
  pause
  exit /b 1
)
exit /b 0

:check_ready
if not exist "%VENV_PYTHON%" exit /b 1
"%VENV_PYTHON%" -c "import fastapi, faster_whisper, multipart, psutil, uvicorn" >nul 2>&1
if errorlevel 1 exit /b 1
where ffmpeg >nul 2>&1
if errorlevel 1 exit /b 1
where ffprobe >nul 2>&1
if errorlevel 1 exit /b 1
exit /b 0
