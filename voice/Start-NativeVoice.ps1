[CmdletBinding()]
param(
    [ValidateSet('STT', 'TTS', 'Model', 'Gateway', 'Voice', 'All', 'Status')]
    [string]$Action = 'Status'
)

$ErrorActionPreference = 'Stop'
$python = 'E:\SCC-Voice\asr-env\Scripts\python.exe'
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
    Push-Location -LiteralPath $repository
    $locationPushed = $true
    Write-Host "SCC Voice: $Action" -ForegroundColor Cyan
    & $python -u $coordinator $Action.ToLowerInvariant()
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
