@echo off
cd /d "%~dp0.."
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0use-flash-next-in-codex.ps1" %*
if errorlevel 1 pause
