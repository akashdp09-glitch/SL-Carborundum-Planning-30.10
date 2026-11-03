@echo off
REM Compatibility wrapper. The real selector is runtime_env.py (probe).
cd /d "%~dp0..\.."
where py >nul 2>nul && (set "BOOT=py") || (set "BOOT=python")
%BOOT% "%~dp0runtime_env.py" probe
exit /b %ERRORLEVEL%
