[CmdletBinding()]
param(
    [ValidateSet('STT', 'TTS', 'Model', 'Gateway', 'Voice', 'All', 'Status')]
    [string]$Action = 'Status',
    [string]$PythonExecutable = $env:SCC_VOICE_PYTHON,
    [string]$BotConfig = $env:SCC_VOICE_BOT_CONFIG,
    [string]$NativeConfig = $env:SCC_VOICE_NATIVE_CONFIG
)

$ErrorActionPreference = 'Stop'
$python = $PythonExecutable
if ([string]::IsNullOrWhiteSpace($python)) {
    $python = Join-Path $PSScriptRoot 'native-bridge\.venv\Scripts\python.exe'
}
$repository = Split-Path -Parent $PSScriptRoot
$coordinator = Join-Path $PSScriptRoot 'native-start\start_services.py'
$result = 1
$locationPushed = $false

try {
    foreach ($requiredFile in @($python, $coordinator)) {
        if (-not (Test-Path -LiteralPath $requiredFile -PathType Leaf)) {
            throw "Erforderliche Datei fehlt: $requiredFile"
        }
    }
    $python = (Resolve-Path -LiteralPath $python).ProviderPath
    Push-Location -LiteralPath $repository
    $locationPushed = $true
    Write-Host "SCC Voice: $Action" -ForegroundColor Cyan
    $coordinatorArguments = @('-u', $coordinator, $Action.ToLowerInvariant())
    if ($PSBoundParameters.ContainsKey('BotConfig') -or $BotConfig) { $coordinatorArguments += @('--bot-config', $BotConfig) }
    if ($PSBoundParameters.ContainsKey('NativeConfig') -or $NativeConfig) { $coordinatorArguments += @('--native-config', $NativeConfig) }
    & $python @coordinatorArguments
    $result = $LASTEXITCODE
    if ($result -ne 0) {
        Write-Host "SCC Voice wurde mit Fehlercode $result beendet. Details stehen oben." -ForegroundColor Red
    }
}
catch {
    Write-Host "SCC Voice konnte nicht gestartet werden: $($_.Exception.Message)" -ForegroundColor Red
    $result = 1
}
finally {
    if ($locationPushed) {
        Pop-Location
    }
}

# Desktop shortcuts use -NoExit, keeping diagnostics visible after this script exits.
exit $result
