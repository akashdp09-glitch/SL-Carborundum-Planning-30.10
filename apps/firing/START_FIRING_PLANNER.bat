@echo off
setlocal
cd /d "%~dp0"
title SL PPC FIRING PLANNER F12P TEST SELECTOR

where py >nul 2>nul
if %errorlevel%==0 (
    set "PY=py"
) else (
    set "PY=python"
)

%PY% -c "import streamlit,pandas,plotly,openpyxl,numpy" >nul 2>nul
if errorlevel 1 (
    echo ERROR: Required Python libraries are missing.
    echo Please run the same Python environment that previously ran the firing planner.
    pause
    exit /b 1
)

%PY% -c "import reportlab" >nul 2>nul
if errorlevel 1 (
    echo WARNING: ReportLab is not installed. Planner will run, but PDF operator export may be unavailable.
)

REM Fresh port avoids stale browser JavaScript chunks from the older localhost:8514 session.
set "PORT=8537"
echo Starting SL PPC Firing Planner F12P TEST SELECTOR on fresh port %PORT% ...
start "SL Firing Planner F12P TEST SELECTOR" /min cmd /c "%PY% -m streamlit run firing_tomorrow_fast.py --server.port %PORT% --server.headless true --browser.gatherUsageStats false"
timeout /t 4 /nobreak >nul
start "" "http://localhost:%PORT%"
exit /b 0
