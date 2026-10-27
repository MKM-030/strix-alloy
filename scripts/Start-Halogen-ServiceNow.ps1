#requires -Version 5.1
<#
.SYNOPSIS
Runs the managed Halogen endpoint in this console for a local API client.
.DESCRIPTION
Uses the existing project Python environment and normal controller/backend
ownership, admission, reserve and cleanup rules. No credentials are printed.
The default Current4K profile pairs a 4096-token prefill chunk with a 4096-token
arena; Current8K explicitly pairs 8192 with 8192. Halogen defaults to installed
0.18.10. Select -HalogenVersion 0.18.16 explicitly for the installed update.
Measured32K is an opt-in preset for the tested 0.18.15 stock configuration:
32K context/pool, 8K chunk/arena, adaptive gate 0.90, Flexible cache,
prefetch off, Vision On and Thinking Off/low. It requires the existing stable
ServiceNow token file and rejects conflicting explicit selector settings.
MeasuredText32K selects the tested 0.18.16 text configuration with the same
32K context/pool, 8K chunk/arena and adaptive gate, but Cache Off and Vision Off.
Thinking remains Off/low and prefetch remains off. ConsoleTrace is opt-in.
HistoricalStock requires -HalogenVersion 0.16.2
and retains the native prefill defaults used by the retained 2026-10-04 stock
benchmark. All profiles select v2 and stock PLD 3,3. Fixed2 is the stable
measured policy. Halogen 0.18.5, 0.18.7, 0.18.8, 0.18.10, 0.18.11, 0.18.15 and 0.18.16 also offer -MtpPolicy Confidence90; Auto
selects the upstream confidence-gated behavior for those versions.
Halogen 0.17.2, 0.17.3, 0.18.0 and 0.18.1 default to Thinking On, medium effort and a 2048-token thinking
budget. Use -Thinking Off to select the supported server default explicitly.
The historical 48.424 tok/s result is workload-specific, not a speed guarantee.
ConsoleTrace opts into request/response content in the console. This script
does not create a transcript or redirect request content to a file.
.EXAMPLE
.\scripts\Start-Halogen-ServiceNow.ps1 -ConsoleTrace
.EXAMPLE
.\scripts\Start-Halogen-ServiceNow.ps1 -Profile Current4K -HalogenVersion 0.18.0 -ConsoleTrace
.EXAMPLE
.\scripts\Start-Halogen-ServiceNow.ps1 -Profile Current4K -HalogenVersion 0.18.1 -ConsoleTrace
.EXAMPLE
.\scripts\Start-Halogen-ServiceNow.ps1 -Profile HistoricalStock -HalogenVersion 0.16.2 -ConsoleTrace
.EXAMPLE
.\scripts\Start-Halogen-ServiceNow.ps1 -PrintOnly
.EXAMPLE
.\scripts\Start-Halogen-ServiceNow.ps1 -Profile Measured32K -ConsoleTrace
.EXAMPLE
.\scripts\Start-Halogen-ServiceNow.ps1 -Profile Measured32K -PrintOnly
.EXAMPLE
.\scripts\Start-Halogen-ServiceNow.ps1 -Profile MeasuredText32K -ConsoleTrace
.EXAMPLE
.\scripts\Start-Halogen-ServiceNow.ps1 -Profile MeasuredText32K -PrintOnly
.EXAMPLE
.\scripts\Start-Halogen-ServiceNow.ps1 -Stop
#>
[CmdletBinding()]
param(
    [ValidateSet('Current8K', 'Current4K', 'HistoricalStock', 'Measured32K', 'MeasuredText32K')]
    [string]$Profile = 'Current4K',
    [ValidateRange(1024, 65535)]
    [int]$Port = 8840,
    [switch]$ConsoleTrace,
    [switch]$PrintOnly,
    [switch]$Status,
    [switch]$Stop,
    [ValidateSet('On', 'Off')]
    [string]$Thinking = 'On',
    [ValidateSet('0.16.2', '0.17.2', '0.17.3', '0.18.0', '0.18.1', '0.18.5', '0.18.7', '0.18.8', '0.18.10', '0.18.11', '0.18.15', '0.18.16')]
    [string]$HalogenVersion = '0.18.10',
    [ValidateSet('Auto', 'Fixed2', 'Confidence90')]
    [string]$MtpPolicy = 'Fixed2',
    [ValidateSet('Off', 'Exact', 'Flexible')]
    [string]$PromptCache = 'Off'
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

$contextCapacity = 262144
$thinkingEffort = 'medium'
$isMeasuredProfile = ($Profile -in @('Measured32K', 'MeasuredText32K'))
$isMeasuredTextProfile = ($Profile -eq 'MeasuredText32K')
if ($isMeasuredProfile) {
    $measuredVersion = if ($isMeasuredTextProfile) { '0.18.16' } else { '0.18.15' }
    $measuredCache = if ($isMeasuredTextProfile) { 'Off' } else { 'Flexible' }
    if (($PSBoundParameters.ContainsKey('HalogenVersion') -and $HalogenVersion -ne $measuredVersion) -or
        ($PSBoundParameters.ContainsKey('Thinking') -and $Thinking -ne 'Off') -or
        ($PSBoundParameters.ContainsKey('MtpPolicy') -and $MtpPolicy -notin @('Auto', 'Confidence90')) -or
        ($PSBoundParameters.ContainsKey('PromptCache') -and $PromptCache -ne $measuredCache)) {
        throw ('{0} requires Halogen {1}, Thinking Off, adaptive MTP (Auto or Confidence90), and {2} cache.' -f $Profile, $measuredVersion, $measuredCache)
    }
    $HalogenVersion = $measuredVersion
    $Thinking = 'Off'
    $MtpPolicy = 'Confidence90'
    $PromptCache = $measuredCache
    $contextCapacity = 32768
    $thinkingEffort = 'low'
}

if ($Profile -eq 'HistoricalStock' -and $HalogenVersion -ne '0.16.2') {
    throw 'HistoricalStock requires explicit -HalogenVersion 0.16.2 for the retained 2026-10-04 stock profile.'
}
if ($HalogenVersion -notin @('0.17.2', '0.17.3', '0.18.0', '0.18.1', '0.18.5', '0.18.7', '0.18.8', '0.18.10', '0.18.11', '0.18.15', '0.18.16') -and $PSBoundParameters.ContainsKey('Thinking')) {
    throw 'Thinking server defaults require a managed Halogen 0.17.2 or newer.'
}
if ($MtpPolicy -eq 'Confidence90' -and $HalogenVersion -notin @('0.18.5', '0.18.7', '0.18.8', '0.18.10', '0.18.11', '0.18.15', '0.18.16')) {
    throw 'Confidence90 requires managed Halogen 0.18.5 or newer supported here.'
}

# make_profile reads installed metadata and token-file paths, not token values.
# Keep the normal generator as the source of endpoint and readiness settings.
$profileCode = @'
import json, sys
sys.path.insert(0, sys.argv[1])
from manage import make_profile
print(json.dumps(make_profile('Halogen', 'v2', int(sys.argv[4]), sys.argv[3], sys.argv[2])))
'@
$profileJson = & $python -u -B -c $profileCode $server $HalogenVersion $PromptCache $contextCapacity
if ($LASTEXITCODE -ne 0) {
    throw 'The installed Halogen profile could not be prepared; no engine was launched.'
}
$configuration = ($profileJson -join [Environment]::NewLine) | ConvertFrom-Json
# Preserve the public ServiceNow credential across backend-version changes.
# The backend's own token_file remains separately configured by make_profile.
$stableApiToken = Join-Path $server '.local\servicenow-api-token.txt'
if (Test-Path -LiteralPath $stableApiToken -PathType Leaf) {
    $configuration.token_file = $stableApiToken
} elseif ($isMeasuredProfile) {
    throw ($Profile + ' requires the existing server/.local/servicenow-api-token.txt; no replacement credential was created.')
}
$windowsPowerShell = Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\powershell.exe'
if (-not (Test-Path -LiteralPath $windowsPowerShell -PathType Leaf)) {
    throw 'Native Windows PowerShell 5.1 is required for the managed telemetry helper.'
}
$configuration.engine | Add-Member -NotePropertyName 'launcher' -NotePropertyValue 'python' -Force
$configuration.engine | Add-Member -NotePropertyName 'python_executable' -NotePropertyValue $python -Force
$configuration.engine.powershell = $windowsPowerShell
$configuration.engine | Add-Member -NotePropertyName 'speculation_policy' `
    -NotePropertyValue ([pscustomobject]@{ HALOGEN_PLD = '3,3' }) -Force
if ($HalogenVersion -notin @('0.18.5', '0.18.7', '0.18.8', '0.18.10', '0.18.11', '0.18.15', '0.18.16') -or $MtpPolicy -eq 'Fixed2') {
    $configuration.engine | Add-Member -NotePropertyName 'draft_tokens' -NotePropertyValue 2 -Force
}
if ($HalogenVersion -in @('0.18.5', '0.18.7', '0.18.8', '0.18.10', '0.18.11', '0.18.15', '0.18.16')) {
    $gate = if ($MtpPolicy -eq 'Fixed2') { '0' } else { '0.90' }
    $configuration.engine.speculation_policy | Add-Member -NotePropertyName 'HALOGEN_MTP_GATE_P' -NotePropertyValue $gate -Force
}
if ($Profile -in @('Current8K', 'Current4K', 'Measured32K', 'MeasuredText32K')) {
    $prefillTokens = if ($Profile -eq 'Current4K') { 4096 } else { 8192 }
    $configuration.engine | Add-Member -NotePropertyName 'prefill_chunk' -NotePropertyValue $prefillTokens -Force
    $configuration.engine | Add-Member -NotePropertyName 'max_prefill_tokens' -NotePropertyValue $prefillTokens -Force
}
if ($HalogenVersion -in @('0.17.2', '0.17.3', '0.18.0', '0.18.1', '0.18.5', '0.18.7', '0.18.8', '0.18.10', '0.18.11', '0.18.15', '0.18.16')) {
    $configuration.engine | Add-Member -NotePropertyName 'api_defaults' `
        -NotePropertyValue ([pscustomobject]@{
            enable_thinking = ($Thinking -eq 'On')
            reasoning_effort = $thinkingEffort
            max_thinking_tokens = 2048
        }) -Force
}
if ($isMeasuredProfile) {
    $configuration.backend.expected | Add-Member -NotePropertyName 'vision.enabled' -NotePropertyValue (-not $isMeasuredTextProfile) -Force
    $configuration.engine | Add-Member -NotePropertyName 'disable_vision' -NotePropertyValue $isMeasuredTextProfile -Force
    $configuration.engine | Add-Member -NotePropertyName 'kernel_controls' `
        -NotePropertyValue ([pscustomobject]@{ HALOGEN_DECODE_PREFETCH = 0 }) -Force
}
$configuration | Add-Member -NotePropertyName 'console_trace' `
    -NotePropertyValue ([bool]$ConsoleTrace.IsPresent) -Force

Write-Host ('Profile: {0}; Halogen {1} v2; MTP policy {2}; PLD 3,3; cache {3}; one request.' -f $Profile, $HalogenVersion, $MtpPolicy, $PromptCache)
Write-Host ('Context capacity: {0} positions (input plus output).' -f $contextCapacity)
if ($HalogenVersion -in @('0.17.2', '0.17.3', '0.18.0', '0.18.1', '0.18.5', '0.18.7', '0.18.8', '0.18.10', '0.18.11', '0.18.15', '0.18.16')) {
    Write-Host ('Thinking default: {0}; {1} effort; thinking budget: 2048 tokens. Requests can override these defaults.' -f $Thinking, $thinkingEffort)
}
if ($Profile -in @('Current8K', 'Current4K', 'Measured32K', 'MeasuredText32K')) {
    Write-Host ('Prefill chunk / token arena: {0} / {1}.' -f $configuration.engine.prefill_chunk, $configuration.engine.max_prefill_tokens)
} else {
    Write-Host 'Prefill chunk / token arena: native stock defaults from the historical profile.'
}
Write-Host 'Memory admission uses the selected backend profile, including its vision allowance; runtime reserve: 18 / 18 GiB.'
Write-Host ('Base URL: http://127.0.0.1:{0}/v1' -f $Port)
Write-Host ('Public model: {0}' -f $configuration.backend.identifier)
Write-Host ('API token file: {0}' -f $configuration.token_file)
Write-Host 'Configure the local client with this base URL and model, and load its API key from the token file.'
Write-Host ('Console request/response trace: {0}.' -f $ConsoleTrace.IsPresent)
Write-Host 'Wait for gateway_listening before sending requests. Press Ctrl+C once and wait for STOPPED to finish cleanup.'
if ($PrintOnly) {
    Write-Host 'PrintOnly: no session configuration was written and no engine was launched.'
    if ($isMeasuredProfile) {
        $configuration | ConvertTo-Json -Depth 20
    }
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
