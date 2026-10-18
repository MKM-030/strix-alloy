param([Parameter(Mandatory)][string]$ContainerId,
      [Parameter(Mandatory)][string]$Output,
      [Parameter(Mandatory)][ValidateSet('ready','inference','final')][string]$Phase)
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'reddit_halogen_controller.ps1')
if ($ContainerId -notmatch '^[0-9a-f]{64}$') { throw 'Exact container ID required' }
$record = Write-MemoryObservation -ContainerId $ContainerId -Path $Output -Phase $Phase
if ($record.windows.availableBytes -lt 12GB -or
    ($record.windows.commitLimitBytes-$record.windows.committedBytes) -lt 12GB) {
    throw 'Memory observation crossed retained floor'
}
