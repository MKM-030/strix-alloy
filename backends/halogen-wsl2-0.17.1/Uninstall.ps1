#requires -Version 5.1
[CmdletBinding()]
param()
$ErrorActionPreference='Stop'
$nativePowerShell=Join-Path ([Environment]::GetFolderPath('System')) 'WindowsPowerShell\v1.0\powershell.exe'
$originalPowerShellHost=$env:ALLOY_POWERSHELL_HOST
try {
    $env:ALLOY_POWERSHELL_HOST=$nativePowerShell
    & (Get-Command python -ErrorAction Stop).Source -B (Join-Path $PSScriptRoot 'scripts/portable.py') uninstall
    $code=$LASTEXITCODE
} finally { $env:ALLOY_POWERSHELL_HOST=$originalPowerShellHost }
exit $code
