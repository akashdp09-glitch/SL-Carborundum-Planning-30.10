@echo off
setlocal EnableExtensions
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\windows\create_desktop_shortcut.ps1"
if errorlevel 1 (
  echo Could not create the desktop shortcut. You can still start the program with START_SL_CARBORUNDUM_PLANNING_CENTER.bat.
  exit /b 1
)
echo Desktop shortcut ready: SL Carborundum Planning Center
exit /b 0
