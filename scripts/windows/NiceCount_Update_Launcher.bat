@echo off
setlocal

set "REPO_URL=https://github.com/gianovembrian/nicecount.git"
set "TARGET_DIR=C:\NiceCount"
set "PG_USER=postgres"
set "PG_PASSWORD=postgres"
set "DB_NAME=vehicle_count"

echo.
echo ============================================
echo   NiceCount Windows Update Launcher
echo ============================================
echo.
echo Repo      : %REPO_URL%
echo TargetDir : %TARGET_DIR%
echo Database  : %DB_NAME%
echo.
echo If your PostgreSQL password or install path is different,
echo edit this BAT file before running it.
echo.

powershell -NoProfile -ExecutionPolicy Bypass -Command "Invoke-WebRequest -Uri 'https://raw.githubusercontent.com/gianovembrian/nicecount/main/scripts/windows/update_windows.ps1' -OutFile $env:TEMP\update_nicecount.ps1; & $env:TEMP\update_nicecount.ps1 -RepoUrl '%REPO_URL%' -TargetDir '%TARGET_DIR%' -PgUser '%PG_USER%' -PgPassword '%PG_PASSWORD%' -DatabaseName '%DB_NAME%' -OpenBrowser"
set "EXITCODE=%ERRORLEVEL%"

echo.
if "%EXITCODE%"=="0" (
  echo NiceCount update completed.
) else (
  echo NiceCount update failed.
)
echo Press any key to close.
pause >nul

endlocal
exit /b %EXITCODE%
