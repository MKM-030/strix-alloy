#requires -Version 7.0
[CmdletBinding()]
param(
 [ValidateSet('Halogen','GUFO','Projfix')][string]$Backend='Halogen',
 [ValidateSet('w4b','v2')][string]$Checkpoint='v2',
 [ValidateRange(4096,262144)][int]$ContextSize=129024,
 [ValidateSet('Off','Exact','Flexible')][string]$PromptCache='Off',
 [ValidateRange(1024,65535)][int]$Port=8840,
 [switch]$PrintOnly,[switch]$Stop,[switch]$Status,[switch]$Logs
)
$ErrorActionPreference='Stop'
if(@($PrintOnly,$Stop,$Status,$Logs|Where-Object{$_}).Count -gt 1){throw 'Select only one control'}
$python=Join-Path $PSScriptRoot '.local/venv/Scripts/python.exe'
if(-not(Test-Path $python)){throw 'Run server/Setup.ps1 first; the gateway has its own Python environment'}
if($Logs){Get-Content (Join-Path $PSScriptRoot '.local/controller.log') -Tail 50 -Wait; exit 0}
$action=if($Stop){'stop'}elseif($Status){'status'}elseif($PrintOnly){'describe'}else{'start'}
& $python -u -B (Join-Path $PSScriptRoot 'manage.py') $action `
 --backend $Backend --checkpoint $Checkpoint --context $ContextSize --prompt-cache $PromptCache --port $Port
exit $LASTEXITCODE
