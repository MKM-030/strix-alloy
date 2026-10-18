@echo off
rem Explicit opt-in GUFO service entry point. All validation is in the PowerShell wrapper.
powershell.exe -NoProfile -File "%~dp0launch-gufo-flash-next.ps1" %*
exit /b %ERRORLEVEL%
