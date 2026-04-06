@echo off
setlocal
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0update_windows.ps1" %*
endlocal
