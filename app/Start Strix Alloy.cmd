@echo off
REM Start Strix Alloy - double-click entry point.
REM Resolves its own location so it works from any install directory, including paths with spaces.
setlocal
set "HERE=%~dp0"
set "PS=%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe"
"%PS%" -NoProfile -ExecutionPolicy Bypass -File "%HERE%start-strix-alloy.ps1" %*
if errorlevel 1 (
  echo.
  echo Start failed. See the message above, or run:  app\start-strix-alloy.ps1 -Action status
  pause
)
endlocal
