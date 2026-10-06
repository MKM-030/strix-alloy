#requires -Version 5.1
<#
.SYNOPSIS
Runs the managed Halogen endpoint in this console for a local API client.
.DESCRIPTION
Uses the existing project Python environment and normal controller/backend
ownership, admission, reserve and cleanup rules. No credentials are printed.
Current8K explicitly pairs an 8192-token prefill chunk with an 8192-token arena.
HistoricalStock retains the native prefill defaults used by the retained
2026-10-04 stock benchmark. Both select v2, MTP depth 2 and stock PLD 3,3.
The historical 48.424 tok/s result is workload-specific, not a speed guarantee.
ConsoleTrace opts into request/response content in the console. This script
does not create a transcript or redirect request content to a file.
.EXAMPLE
.\scripts\Start-Halogen-ServiceNow.ps1 -ConsoleTrace
.EXAMPLE
.\scripts\Start-Halogen-ServiceNow.ps1 -Profile HistoricalStock -ConsoleTrace
.EXAMPLE
.\scripts\Start-Halogen-ServiceNow.ps1 -PrintOnly
.EXAMPLE
.\scripts\Start-Halogen-ServiceNow.ps1 -Stop
#>
[CmdletBinding()]
param(
    [ValidateSet('Current8K', 'HistoricalStock')]
    [string]$Profile = 'Current8K',
    [ValidateRange(1024, 65535)]
    [int]$Port = 8840,
    [switch]$ConsoleTrace,
    [switch]$PrintOnly,
    [switch]$Status,
    [switch]$Stop
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version 2.0
if (@($PrintOnly.IsPresent, $Status.IsPresent, $Stop.IsPresent |
        Where-Object { $_ }).Count -gt 1) {
    throw 'Select only one of PrintOnly, Status or Stop.'
}
if ($Port -eq 8731) {
    throw 'The public port must differ from the Halogen backend port 8731.'
}

$repository = Split-Path -Parent $PSScriptRoot
$server = Join-Path $repository 'server'
$python = Join-Path $server '.local\venv\Scripts\python.exe'
$controller = Join-Path $server 'controller.py'
if (-not (Test-Path -LiteralPath $python -PathType Leaf)) {
    throw 'The existing server/.local/venv Python environment is required. Follow server/README.md to set it up.'
}
if (-not (Test-Path -LiteralPath $controller -PathType Leaf)) {
    throw 'The managed server controller is missing from this checkout.'
}

# These controls address only the run identity retained by the controller.
# Starting never requests a stop, deletes a lock or adopts a running engine.
if ($Stop -or $Status) {
    $action = if ($Stop) { 'stop' } else { 'status' }
    & $python -u -B $controller $action
    exit $LASTEXITCODE
}

# make_profile reads installed metadata and token-file paths, not token values.
# Keep the normal generator as the source of endpoint and readiness settings.
$profileCode = @'
import json, sys
sys.path.insert(0, sys.argv[1])
from manage import make_profile
print(json.dumps(make_profile('Halogen', 'v2', 262144, 'Off')))
'@
$profileJson = & $python -u -B -c $profileCode $server
if ($LASTEXITCODE -ne 0) {
    throw 'The installed Halogen profile could not be prepared; no engine was launched.'
}
$configuration = ($profileJson -join [Environment]::NewLine) | ConvertFrom-Json
$windowsPowerShell = Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\powershell.exe'
if (-not (Test-Path -LiteralPath $windowsPowerShell -PathType Leaf)) {
    throw 'Native Windows PowerShell 5.1 is required for the managed telemetry helper.'
}
$configuration.engine | Add-Member -NotePropertyName 'launcher' -NotePropertyValue 'python' -Force
$configuration.engine | Add-Member -NotePropertyName 'python_executable' -NotePropertyValue $python -Force
$configuration.engine.powershell = $windowsPowerShell
$configuration.engine | Add-Member -NotePropertyName 'draft_tokens' -NotePropertyValue 2 -Force
$configuration.engine | Add-Member -NotePropertyName 'speculation_policy' `
    -NotePropertyValue ([pscustomobject]@{ HALOGEN_PLD = '3,3' }) -Force
if ($Profile -eq 'Current8K') {
    $configuration.engine | Add-Member -NotePropertyName 'prefill_chunk' -NotePropertyValue 8192 -Force
    $configuration.engine | Add-Member -NotePropertyName 'max_prefill_tokens' -NotePropertyValue 8192 -Force
}
$configuration | Add-Member -NotePropertyName 'console_trace' `
    -NotePropertyValue ([bool]$ConsoleTrace.IsPresent) -Force

Write-Host ('Profile: {0}; Halogen 0.16.2 v2; MTP depth 2; PLD 3,3; cache Off; one request.' -f $Profile)
Write-Host 'Context capacity: 262144 positions (input plus output).'
if ($Profile -eq 'Current8K') {
    Write-Host 'Prefill chunk / token arena: 8192 / 8192.'
} else {
    Write-Host 'Prefill chunk / token arena: native stock defaults from the historical profile.'
}
Write-Host 'Memory admission: 44 GiB free physical / 131 GiB commit headroom; runtime reserve: 18 / 18 GiB.'
Write-Host ('Base URL: http://127.0.0.1:{0}/v1' -f $Port)
Write-Host ('Public model: {0}' -f $configuration.backend.identifier)
Write-Host ('API token file: {0}' -f $configuration.token_file)
Write-Host 'Configure the local client with this base URL and model, and load its API key from the token file.'
Write-Host ('Console request/response trace: {0}.' -f $ConsoleTrace.IsPresent)
Write-Host 'Wait for gateway_listening before sending requests. Press Ctrl+C once and wait for STOPPED to finish cleanup.'
if ($PrintOnly) {
    Write-Host 'PrintOnly: no session configuration was written and no engine was launched.'
    exit 0
}

# A fresh file prevents another invocation from rewriting this run's profile.
# It contains token-file references only and is retained as lifecycle evidence.
$sessionDirectory = Join-Path $server '.local\servicenow-sessions'
[void][IO.Directory]::CreateDirectory($sessionDirectory)
$sessionFile = Join-Path $sessionDirectory (([Guid]::NewGuid().ToString('N')) + '.json')
$serialized = $configuration | ConvertTo-Json -Depth 20
[IO.File]::WriteAllText($sessionFile, $serialized, (New-Object Text.UTF8Encoding($false)))
Write-Host ('Session configuration: {0}' -f $sessionFile)

# Direct foreground invocation leaves stdin and Ctrl+C attached to Python.
# controller.py owns the singleton lease, job and normal backend stop/recovery.
& $python -u -B $controller run --config $sessionFile --port $Port
exit $LASTEXITCODE
