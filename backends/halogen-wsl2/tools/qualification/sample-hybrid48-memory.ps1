param(
    [Parameter(Mandatory)][string]$ContainerId,
    [Parameter(Mandatory)][string]$Output,
    [Parameter(Mandatory)][ValidateSet('ready','inference','final')][string]$Phase
)
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'qualify-hybrid48-model.ps1')
Initialize-PublicMachine
try { $null = Write-MemoryObservation -ContainerId $ContainerId -Path $Output -Phase $Phase }
catch { Write-Error "Memory observation failed: $_"; exit 2 }
