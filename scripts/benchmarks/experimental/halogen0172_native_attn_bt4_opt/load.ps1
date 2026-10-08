param([Parameter(Mandatory=$true)][ValidateSet('before','candidate','after')][string]$Window)
$ErrorActionPreference = 'Stop'
$games = @(Get-Process | Where-Object { $_.ProcessName -match '^(League|Riot)' } |
    Select-Object Id, ProcessName)
$gpu = @(Get-CimInstance -ClassName Win32_PerfFormattedData_GPUPerformanceCounters_GPUEngine |
    Where-Object { [double]$_.UtilizationPercentage -ge 5 } |
    Select-Object Name, UtilizationPercentage)
$record = [pscustomobject]@{
    utc = [DateTime]::UtcNow.ToString('o')
    games = $games
    gpu = $gpu
    observation_only = $true
}
$record | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $PSScriptRoot ($Window + '-premeasurement-load.json')) -Encoding UTF8
$record | ConvertTo-Json -Depth 5
if ($games.Count -gt 0) { throw 'League/Riot process present; root must assess this observation before measuring.' }
if ($gpu.Count -gt 0) { throw 'GPU load observed; root must assess this observation before measuring.' }
