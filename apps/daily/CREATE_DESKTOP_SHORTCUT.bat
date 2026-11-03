@echo off
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -Command "$s=(New-Object -COM WScript.Shell).CreateShortcut([Environment]::GetFolderPath('Desktop')+'\SL Daily Planner.lnk');$s.TargetPath='%~dp0START_DAILY_PLANNER.bat';$s.WorkingDirectory='%~dp0';$s.IconLocation='%~dp0SL_DAILY_PLANNER_ICON.ico,0';$s.Description='SL Carborundum Planning Department - Daily Planner';$s.Save()"
echo Desktop shortcut created: SL Daily Planner
pause
