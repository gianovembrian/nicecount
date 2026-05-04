@echo off
setlocal

set "TARGET_DIR=C:\NiceCount"
set "APP_PORT=8000"

echo.
echo ============================================
echo   NiceCount Run Launcher
echo ============================================
echo.
echo TargetDir : %TARGET_DIR%
echo Port      : %APP_PORT%
echo.
echo Jika path instalasi berbeda, edit file BAT ini sebelum dijalankan.
echo.

powershell -NoProfile -ExecutionPolicy Bypass -File "%TARGET_DIR%\scripts\windows\run_local_windows.ps1" -TargetDir "%TARGET_DIR%" -AppPort %APP_PORT% -OpenBrowser
set "EXITCODE=%ERRORLEVEL%"

echo.
if "%EXITCODE%"=="0" (
    echo NiceCount berhasil dijalankan.
) else (
    echo NiceCount gagal dijalankan. Tekan sembarang tombol untuk menutup.
    pause >nul
)

endlocal
exit /b %EXITCODE%
