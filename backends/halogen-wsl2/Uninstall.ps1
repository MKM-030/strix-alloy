#requires -Version 7.0
param()
$ErrorActionPreference='Stop'
& (Get-Command python -ErrorAction Stop).Source -B (Join-Path $PSScriptRoot 'scripts/package.py') uninstall
if($LASTEXITCODE -ne 0){throw 'Uninstall refused; generated files were not silently overwritten or removed.'}
