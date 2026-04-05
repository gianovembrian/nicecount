@echo off
setlocal
powershell -ExecutionPolicy Bypass -NoProfile -File "%~dp0install_windows.ps1" %*
