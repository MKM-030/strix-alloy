#requires -Version 7.0
[CmdletBinding()]
param()
$ErrorActionPreference='Stop'
& (Get-Command python -ErrorAction Stop).Source -B (Join-Path $PSScriptRoot 'scripts/portable.py') uninstall
exit $LASTEXITCODE
