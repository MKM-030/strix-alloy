@echo off
REM Stop Strix Alloy - stops only the server this installation started.
setlocal
set "HERE=%~dp0"
set "PS=%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe"
"%PS%" -NoProfile -ExecutionPolicy Bypass -File "%HERE%start-strix-alloy.ps1" -Action stop
timeout /t 3 >nul
endlocal
