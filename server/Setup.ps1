#requires -Version 7.0
[CmdletBinding()]
param([switch]$Install)
$ErrorActionPreference='Stop'
if(-not $Install){Write-Output 'Plan: create an isolated Python venv and install server/requirements.txt. No model, driver, BIOS or WSL change. Use -Install to execute.'; exit 0}
$venv=Join-Path $PSScriptRoot '.local/venv'
$python=Join-Path $venv 'Scripts/python.exe'
if(-not(Test-Path $python)){
 if(Test-Path $venv){throw 'Incomplete environment exists; preserve it and inspect before retrying'}
 & python -m venv $venv
 if($LASTEXITCODE -ne 0){throw 'Could not create isolated Python environment'}
}
& $python -m pip install --disable-pip-version-check -r (Join-Path $PSScriptRoot 'requirements.txt')
if($LASTEXITCODE -ne 0){throw 'Gateway dependency installation failed'}
& $python -B -m unittest discover -s (Join-Path $PSScriptRoot 'tests') -v
if($LASTEXITCODE -ne 0){throw 'Gateway tests failed; no engine was launched'}
Write-Output 'Gateway installed. Backend installation/model files are separate; no running server was required.'
