@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title SL Carborundum - install isolated environment
set "SL_VENV=%~dp0RUNTIME\venv"
set "PIP_CACHE_DIR=%~dp0RUNTIME\pip-cache"
set "TEMP=%~dp0RUNTIME\tmp"
set "TMP=%~dp0RUNTIME\tmp"
if not exist "%TEMP%" mkdir "%TEMP%"
if not exist "%PIP_CACHE_DIR%" mkdir "%PIP_CACHE_DIR%"

REM Bootstrap only: any Python that can run the helper. The helper picks a
REM supported interpreter or installs private Python 3.12 under RUNTIME (no PATH
REM change/admin rights), then creates the app venv. pandas is never compiled.
set "BOOT="
where py >nul 2>nul && set "BOOT=py"
if not defined BOOT (
  where python >nul 2>nul && set "BOOT=python"
)
if not defined BOOT (
  echo No Python bootstrap was found. Install 64-bit Python 3.12 once:
  echo   https://www.python.org/ftp/python/3.12.15/python-3.12.15-amd64.exe
  echo Add-to-PATH is not required. Then run this file again.
  echo Do not install Visual Studio for this software.
  pause
  exit /b 1
)

echo Bootstrap: %BOOT%
%BOOT% -c "import sys; print(sys.version); print(sys.executable)"
echo.

%BOOT% "%~dp0scripts\windows\runtime_env.py" install
set "RC=%ERRORLEVEL%"
if not "%RC%"=="0" (
  echo.
  echo Installation stopped. Streamlit was not started.
  echo Factory data folders were not changed.
  echo If you saw vswhere.exe / meson / metadata-generation-failed: that is the
  echo old installer. This one refuses unsupported Python before pip.
  echo See docs\WINDOWS_INSTALL.md
  pause
  exit /b %RC%
)
echo.
pause
exit /b 0
