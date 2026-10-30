@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title SL Carborundum Planning Center

echo.
echo SL Carborundum Planning Center
echo The .sha256 file is only a download check — do not copy it here.
echo.

if not exist "%~dp0hub.py" (
  echo Open the unzipped folder that contains hub.py, then run this file again.
  pause
  exit /b 1
)

if exist "%~dp0SERVER_STORAGE_CONFIG.bat" call "%~dp0SERVER_STORAGE_CONFIG.bat"
if errorlevel 1 (
  echo Storage validation failed. The app was not started, to prevent saving records to the wrong location.
  pause
  exit /b 1
)
if not exist logs mkdir logs

REM Keep one runtime on the existing D: install root so new version folders reuse it.
if defined SL_LEGACY_DATA_ROOT (
  for %%I in ("%SL_LEGACY_DATA_ROOT%\..") do set "SL_RUNTIME_ROOT=%%~fI\RUNTIME"
) else (
  set "SL_RUNTIME_ROOT=%~dp0RUNTIME"
)
set "SL_VENV=%SL_RUNTIME_ROOT%\venv"
set "PIP_CACHE_DIR=%SL_RUNTIME_ROOT%\pip-cache"
set "TEMP=%SL_RUNTIME_ROOT%\tmp"
set "TMP=%SL_RUNTIME_ROOT%\tmp"
if not exist "%TEMP%" mkdir "%TEMP%"
if not exist "%PIP_CACHE_DIR%" mkdir "%PIP_CACHE_DIR%"

call :RESOLVE_VPY

REM Same-folder launches validate the full pinned runtime and its install stamp.
REM A shortcut points here; a ready install goes straight to the interface.
if exist "%VPY%" (
  "%VPY%" "%~dp0scripts\windows\runtime_env.py" ready >nul 2>&1
  if not errorlevel 1 (
    echo Already installed — starting Planning Center
    goto LAUNCH
  )
)

goto INSTALL

:INSTALL
echo First run in this folder: installing the required packages once.
echo The desktop shortcut will open the interface directly on later runs.
echo Factory data folders are not changed.
echo.
set "BOOT="
where py >nul 2>nul && set "BOOT=py"
if not defined BOOT (
  where python >nul 2>nul && set "BOOT=python"
)
if not defined BOOT (
  echo No Python bootstrap was found. Install 64-bit Python 3.12 once,
  echo Add-to-PATH is not required, then run this file again:
  echo   https://www.python.org/ftp/python/3.12.15/python-3.12.15-amd64.exe
  echo Do not install Visual Studio for this software.
  pause
  exit /b 1
)
"%BOOT%" "%~dp0scripts\windows\runtime_env.py" install
if errorlevel 1 (
  echo Install did not finish. See docs\WINDOWS_INSTALL.md
  pause
  exit /b 1
)
call :RESOLVE_VPY
if not exist "%VPY%" (
  echo Application Python is still missing after install.
  pause
  exit /b 1
)

:LAUNCH
call "%~dp0CREATE_DESKTOP_SHORTCUT.bat"
if errorlevel 1 echo Shortcut was not created automatically. Run CREATE_DESKTOP_SHORTCUT.bat once from this folder.
echo.
echo Starting Streamlit at http://127.0.0.1:8510
echo Phones on the factory LAN: http://THIS-PC:8510  (shop floor: /?page=floor)
echo Leave this window open. The browser opens by itself.
echo Close Daily / Firing / phone windows from an older ZIP folder first.
echo.
"%VPY%" -m streamlit run "%~dp0hub.py" --server.port 8510 --server.address 0.0.0.0 --browser.serverAddress 127.0.0.1 --server.headless false --server.enableCORS false --server.enableXsrfProtection false --browser.gatherUsageStats false
set "RC=%ERRORLEVEL%"
echo.
if not "%RC%"=="0" (
  echo Streamlit stopped. Close any other Planning Center window using port 8510, then try again.
)
pause
exit /b %RC%

:RESOLVE_VPY
if defined SL_VENV (
  set "VPY=%SL_VENV%\Scripts\python.exe"
) else (
  set "VPY=%~dp0RUNTIME\venv\Scripts\python.exe"
)
if not exist "%VPY%" (
  if exist "%~dp0.venv\Scripts\python.exe" set "VPY=%~dp0.venv\Scripts\python.exe"
)
goto :eof
