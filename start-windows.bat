@echo off
setlocal
cd /d "%~dp0"
if not exist .venv\Scripts\python.exe (
  py -3.12 -m venv .venv
  if errorlevel 1 py -3 -m venv .venv
  if errorlevel 1 python -m venv .venv
  if not exist .venv\Scripts\python.exe (
    echo Python 3.11-3.13 is required.
    pause
    exit /b 1
  )
  .venv\Scripts\python.exe -m pip install --upgrade pip
  .venv\Scripts\python.exe -m pip install -r requirements.txt
)
.venv\Scripts\python.exe run.py
endlocal
