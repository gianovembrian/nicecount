@echo off
setlocal

set "REPO_URL=https://github.com/gianovembrian/nicecount.git"
set "TARGET_DIR=C:\NiceCount"
set "PG_USER=postgres"
set "PG_PASSWORD=postgres"
set "DB_NAME=vehicle_count"

echo.
echo ============================================
echo   NiceCount Update (Force Reset) Launcher
echo ============================================
echo.
echo PERHATIAN: Script ini akan mereset repo ke versi GitHub secara paksa.
echo Gunakan hanya jika update biasa gagal atau repo rusak.
echo.
echo Repo      : %REPO_URL%
echo TargetDir : %TARGET_DIR%
echo Database  : %DB_NAME%
echo.
echo Jika password PostgreSQL atau path instalasi berbeda,
echo edit file BAT ini sebelum dijalankan.
echo.
pause

powershell -NoProfile -ExecutionPolicy Bypass -Command "Invoke-WebRequest -Uri 'https://raw.githubusercontent.com/gianovembrian/nicecount/main/scripts/windows/update_windows.ps1' -OutFile $env:TEMP\update_force_nicecount.ps1; & $env:TEMP\update_force_nicecount.ps1 -RepoUrl '%REPO_URL%' -TargetDir '%TARGET_DIR%' -PgUser '%PG_USER%' -PgPassword '%PG_PASSWORD%' -DatabaseName '%DB_NAME%' -OpenBrowser"
set "EXITCODE=%ERRORLEVEL%"

echo.
if "%EXITCODE%"=="0" (
    echo NiceCount berhasil diperbarui.
) else (
    echo NiceCount gagal diperbarui. Tekan sembarang tombol untuk menutup.
    pause >nul
)

endlocal
exit /b %EXITCODE%
