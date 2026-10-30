@echo off
setlocal
cd /d "%~dp0"
if exist SERVER_STORAGE_CONFIG.bat call SERVER_STORAGE_CONFIG.bat
where py >nul 2>nul
if %errorlevel%==0 (set "PY=py") else (set "PY=python")
echo Source folder: %SL_COMPANY_DATA%
echo This rebuild replaces the bundled reference snapshot only after a successful build.
%PY% knowledge\build_knowledge_db.py "%SL_COMPANY_DATA%"
if errorlevel 1 (
  echo Knowledge database was not replaced. Check source workbook paths and errors above.
  pause
  exit /b 1
)
echo Knowledge database refreshed. Restart the planning center to reload its snapshot.
pause
