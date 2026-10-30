@echo off
REM LOCAL DATA — this PC's D: drive hosts the app and all factory data.
REM Mobile phones connect to the app over factory Wi-Fi; they do not access D: directly.
REM If you copied CENTRAL_DATA beside this revised program, use that copy first.
REM Existing audit DB, photos, source files and reports are kept in-place; this file does not clear them.
set "SL_LEGACY_DATA_ROOT=D:\SL_Carborundum_Planning_V16.29-rc14\CENTRAL_DATA"
if exist "%~dp0CENTRAL_DATA\" (
  set "SL_SHARED_ROOT=%~dp0CENTRAL_DATA"
) else if exist "%SL_LEGACY_DATA_ROOT%\" (
  set "SL_SHARED_ROOT=%SL_LEGACY_DATA_ROOT%"
) else (
  set "SL_SHARED_ROOT=%~dp0CENTRAL_DATA"
)
set "SL_COMPANY_DATA=%SL_SHARED_ROOT%\COMPANY_DATA"
set "SL_DB_PATH=%SL_SHARED_ROOT%\DATABASE\sl_planning.db"
set "SL_PHOTO_ROOT=%SL_SHARED_ROOT%\PHOTOS"
set "SL_SOURCE_COPY_ROOT=%SL_SHARED_ROOT%\SOURCE_COPIES"
set "SL_REPORT_ROOT=%SL_SHARED_ROOT%\REPORTS"
REM Preserve the operator mobile URL configured on this factory LAN.
set "SL_MOBILE_HOST=176.0.3.99"
if not exist "%SL_SHARED_ROOT%\" mkdir "%SL_SHARED_ROOT%"
for %%D in ("%SL_COMPANY_DATA%" "%SL_SHARED_ROOT%\DATABASE" "%SL_PHOTO_ROOT%\MOBILE_AUDITS" "%SL_PHOTO_ROOT%\QR_SCANS" "%SL_PHOTO_ROOT%\UNIDENTIFIED_PARTS" "%SL_SOURCE_COPY_ROOT%" "%SL_REPORT_ROOT%" "%SL_SHARED_ROOT%\BACKUPS" "%SL_SHARED_ROOT%\CACHE" "%SL_SHARED_ROOT%\DAILY_STATUS" "%SL_SHARED_ROOT%\KPI" "%SL_SHARED_ROOT%\PRODUCTION_WIP") do if not exist "%%~D" mkdir "%%~D"
if errorlevel 1 (
  echo ERROR: Could not create the required folders under %SL_SHARED_ROOT%.
  echo Check that this Windows account can write to the local D: data folder.
  exit /b 1
)
set "SL_STORAGE_TEST=%SL_SHARED_ROOT%\.__sl_planning_write_test.tmp"
>"%SL_STORAGE_TEST%" echo storage-write-test
if errorlevel 1 (
  echo ERROR: This Windows account cannot write to %SL_SHARED_ROOT%.
  echo Check local D: drive permissions, then run this file again.
  exit /b 1
)
del "%SL_STORAGE_TEST%" >nul 2>nul
