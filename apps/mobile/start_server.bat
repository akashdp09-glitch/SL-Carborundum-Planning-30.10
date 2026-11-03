@echo off
setlocal EnableExtensions
cd /d "%~dp0..\.."
title SL Part Tracking - Local D Drive
call "%~dp0..\..\SERVER_STORAGE_CONFIG.bat"
if errorlevel 1 (
  echo Local D: storage could not be opened. Mobile service was not started.
  pause
  exit /b 1
)
set "SL_VENV=%~dp0..\..\RUNTIME\venv"
set "PIP_CACHE_DIR=%~dp0..\..\RUNTIME\pip-cache"
set "TEMP=%~dp0..\..\RUNTIME\tmp"
set "TMP=%~dp0..\..\RUNTIME\tmp"
set "PY=%SL_VENV%\Scripts\python.exe"
if not exist "%PY%" (
  echo Runtime is not installed. Run the main START file first.
  pause
  exit /b 1
)
"%PY%" -c "import fastapi,uvicorn,streamlit,pandas" >nul 2>&1
if errorlevel 1 (
  echo Runtime is incomplete. Run START_SL_CARBORUNDUM_PLANNING_CENTER.bat to install or repair.
  pause
  exit /b 1
)
set "SL_PORT=8000"
echo Starting the tracking service from this D: program folder.
echo Local data: %SL_SHARED_ROOT%
echo Phone: http://176.0.3.99:8000/mobile
echo Live video scanning requires HTTPS; HTTP supports photo upload and manual WO search.
"%PY%" "%~dp0..\..\scripts\windows\start_mobile.py"
if errorlevel 1 (
  echo Tracking service stopped. Check logs\mobile.log and confirm port 8000 is free.
  pause
)
endlocal
