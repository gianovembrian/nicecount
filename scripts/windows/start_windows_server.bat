@echo off
setlocal
if "%~1"=="" (
  pushd "%~dp0..\.."
  powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0start_windows_server.ps1" -UseCurrentDirectory -OpenBrowser
  set "EXITCODE=%ERRORLEVEL%"
  popd
) else (
  powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0start_windows_server.ps1" %*
  set "EXITCODE=%ERRORLEVEL%"
)
if not "%EXITCODE%"=="0" (
  echo.
  echo NiceCount start failed. Press any key to close.
  pause >nul
)
endlocal
exit /b %EXITCODE%
