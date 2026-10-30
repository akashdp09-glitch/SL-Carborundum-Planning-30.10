@echo off
cd /d "%~dp0"
if exist "%LOCALAPPDATA%\SLCarborundum\runtime-venv\Scripts\python.exe" (
  set "PY=%LOCALAPPDATA%\SLCarborundum\runtime-venv\Scripts\python.exe"
) else if exist "%~dp0.venv\Scripts\python.exe" (
  set "PY=%~dp0.venv\Scripts\python.exe"
) else (
  where py >nul 2>nul && (set "PY=py") || (set "PY=python")
)
echo Using: %PY%
echo === 1/2 Compile all Python files ===
"%PY%" -m compileall -q .
echo === 2/2 Scan for undefined names (NameError risk) ===
"%PY%" selftest_undefined_names.py
echo (Last number printed = count of suspicious names. 0 is good.)
pause
