@echo off
setlocal
if "%~1"=="" (
  pushd "%~dp0..\.."
  powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0update_windows.ps1" -UseCurrentDirectory -OpenBrowser
  set "EXITCODE=%ERRORLEVEL%"
  popd
) else (
  powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0update_windows.ps1" %*
  set "EXITCODE=%ERRORLEVEL%"
)
if not "%EXITCODE%"=="0" (
  echo.
  echo NiceCount update failed. Press any key to close.
  pause >nul
)
endlocal
exit /b %EXITCODE%
