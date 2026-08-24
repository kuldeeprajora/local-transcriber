@echo off
setlocal EnableExtensions EnableDelayedExpansion
cd /d "%~dp0"
title Local Transcriber - Safe Windows Setup
set "SETUP_LOG=%CD%\setup-windows.log"
set "VENV_PYTHON=%CD%\.venv\Scripts\python.exe"

> "%SETUP_LOG%" echo Local Transcriber Windows setup started %DATE% %TIME%
echo ============================================================
echo        LOCAL TRANSCRIBER - SAFE WINDOWS SETUP
echo ============================================================
echo This installer tries automatic recovery before it stops.
echo Diagnostic log: %SETUP_LOG%
echo.

echo [1/5] Finding Python 3.12...
call :detect_python
if not defined PYTHON_EXE (
  echo Python was not found. Trying automatic installation with winget...
  where winget >nul 2>&1
  if errorlevel 1 goto :python_manual
  winget install -e --id Python.Python.3.12 --accept-package-agreements --accept-source-agreements
  if errorlevel 1 goto :python_manual
  echo winget Python install exit code: !ERRORLEVEL!>> "%SETUP_LOG%"
  call :detect_python
)
if not defined PYTHON_EXE goto :python_restart
echo Using: %PYTHON_EXE%
"%PYTHON_EXE%" --version

echo.
echo [2/5] Checking the private Python environment...
if exist "%VENV_PYTHON%" (
  "%VENV_PYTHON%" -c "import sys; assert sys.version_info >= (3, 9)" >nul 2>&1
  if errorlevel 1 call :backup_broken_venv
) else if exist .venv (
  call :backup_broken_venv
)

if not exist "%VENV_PYTHON%" (
  echo Creating .venv...
  "%PYTHON_EXE%" -m venv .venv
  if errorlevel 1 (
    echo First environment command failed. Trying ensurepip and venv again...
    "%PYTHON_EXE%" -m ensurepip --upgrade >nul 2>&1
    "%PYTHON_EXE%" -m venv --clear .venv
  )
)
if not exist "%VENV_PYTHON%" goto :venv_error

echo.
echo [3/5] Installing Python dependencies...
"%VENV_PYTHON%" -m ensurepip --upgrade >nul 2>&1
"%VENV_PYTHON%" -m pip install --upgrade pip setuptools wheel
if errorlevel 1 echo WARNING: pip upgrade failed; continuing with the existing pip.

"%VENV_PYTHON%" -m pip install --retries 4 --timeout 60 -r requirements.txt
if errorlevel 1 (
  echo First dependency installation failed.
  echo Retrying without the pip download cache...
  "%VENV_PYTHON%" -m pip cache purge >nul 2>&1
  "%VENV_PYTHON%" -m pip install --no-cache-dir --retries 6 --timeout 90 -r requirements.txt
)
if errorlevel 1 goto :package_error

echo.
echo [4/5] Verifying the transcription backend...
call :verify_python_packages
if errorlevel 1 (
  echo Verification failed. Repairing the Windows backend...
  "%VENV_PYTHON%" -m pip install --no-cache-dir --force-reinstall faster-whisper fastapi "uvicorn[standard]" python-multipart psutil
  if errorlevel 1 goto :verify_error
  call :verify_python_packages
)
if errorlevel 1 goto :verify_error

echo.
echo [5/5] Checking FFmpeg and FFprobe...
call :detect_ffmpeg
if errorlevel 1 (
  where winget >nul 2>&1
  if errorlevel 1 goto :ffmpeg_manual
  echo FFmpeg is missing. Trying automatic installation with winget...
  winget install -e --id Gyan.FFmpeg --accept-package-agreements --accept-source-agreements
  if errorlevel 1 goto :ffmpeg_manual
  echo winget FFmpeg install exit code: !ERRORLEVEL!>> "%SETUP_LOG%"
  set "PATH=%PATH%;%LOCALAPPDATA%\Microsoft\WinGet\Links"
  call :detect_ffmpeg
)
if errorlevel 1 goto :ffmpeg_restart

echo FFmpeg and FFprobe: READY
echo Setup completed successfully.>> "%SETUP_LOG%"
echo.
echo ============================================================
echo SETUP COMPLETE
echo Now double-click start-windows.bat
echo ============================================================
goto :success

:detect_python
set "PYTHON_EXE="
for /f "delims=" %%I in ('py -3.12 -c "import sys; print(sys.executable)" 2^>nul') do if not defined PYTHON_EXE set "PYTHON_EXE=%%I"
if defined PYTHON_EXE exit /b 0
for /f "delims=" %%I in ('py -3 -c "import sys; print(sys.executable)" 2^>nul') do if not defined PYTHON_EXE set "PYTHON_EXE=%%I"
if defined PYTHON_EXE exit /b 0
for /f "delims=" %%I in ('python -c "import sys; print(sys.executable)" 2^>nul') do if not defined PYTHON_EXE set "PYTHON_EXE=%%I"
if defined PYTHON_EXE exit /b 0
if exist "%LOCALAPPDATA%\Programs\Python\Python312\python.exe" set "PYTHON_EXE=%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
if exist "%ProgramFiles%\Python312\python.exe" set "PYTHON_EXE=%ProgramFiles%\Python312\python.exe"
exit /b 0

:backup_broken_venv
set "VENV_BACKUP=.venv-broken-%RANDOM%"
echo Existing .venv is invalid. Preserving it as !VENV_BACKUP!...
move .venv "!VENV_BACKUP!" >nul
if errorlevel 1 goto :venv_error
exit /b 0

:verify_python_packages
"%VENV_PYTHON%" -c "import fastapi, faster_whisper, multipart, psutil, uvicorn; print('Python transcription packages: READY')"
exit /b %ERRORLEVEL%

:detect_ffmpeg
where ffmpeg >nul 2>&1
if errorlevel 1 exit /b 1
where ffprobe >nul 2>&1
if errorlevel 1 exit /b 1
exit /b 0

:python_manual
echo Python automatic installation was unavailable or unsuccessful.>> "%SETUP_LOG%"
echo.
echo SETUP NEEDS ONE MANUAL STEP: PYTHON
echo 1. Install 64-bit Python 3.12 from:
echo    https://python.org/downloads/windows/
echo 2. Enable the Python launcher or Add Python to PATH.
echo 3. Restart this installer. It will continue from there.
goto :failed

:python_restart
echo Python was installed but is not visible in the current terminal.>> "%SETUP_LOG%"
echo.
echo PYTHON WAS INSTALLED OR UPDATED
echo Windows has not exposed it to this window yet.
echo Close this window and run INSTALL-WINDOWS.bat once more.
goto :partial

:venv_error
echo Could not create or repair .venv.>> "%SETUP_LOG%"
echo.
echo SETUP FAILED while creating the private environment.
echo Close programs using this folder and check available disk space.
goto :failed

:package_error
echo Dependency installation failed after normal and no-cache attempts.>> "%SETUP_LOG%"
echo.
echo SETUP FAILED after two package installation attempts.
echo Check the internet connection, VPN, proxy, antivirus, and disk space.
goto :failed

:verify_error
echo Backend verification and forced reinstall failed.>> "%SETUP_LOG%"
echo.
echo SETUP FAILED while repairing the transcription backend.
echo Send setup-windows.log and the error above to the administrator.
goto :failed

:ffmpeg_manual
echo FFmpeg missing and winget unavailable.>> "%SETUP_LOG%"
echo.
echo PYTHON IS READY - FFMPEG NEEDS A MANUAL INSTALL
echo Download a Windows build from https://ffmpeg.org/download.html
echo Add its bin folder to PATH, then restart this installer.
goto :partial

:ffmpeg_restart
echo FFmpeg install requested; a Windows terminal restart may be required.>> "%SETUP_LOG%"
echo.
echo PYTHON IS READY - FFMPEG WAS INSTALLED OR UPDATED
echo Windows has not exposed the new command to this window yet.
echo Close this window, reopen INSTALL-WINDOWS.bat, and it will verify it.
goto :partial

:success
echo.
pause
exit /b 0

:partial
echo.
pause
exit /b 2

:failed
echo See the diagnostic log at: %SETUP_LOG%
echo.
pause
exit /b 1
