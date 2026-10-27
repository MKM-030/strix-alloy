[CmdletBinding()]
param([switch]$CheckOnly)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$Python = Join-Path $PSScriptRoot 'native-bridge\.venv\Scripts\python.exe'
$Coordinator = Join-Path $PSScriptRoot 'native-start\start_current_voice.py'
$exitCode = 1
Write-Host 'ServiceNow Sprache - zentrales lokales Modell und eigene Stimme' -ForegroundColor Cyan
try {
    if (-not (Test-Path -LiteralPath $Python -PathType Leaf)) { throw 'Native Python-Laufzeit fehlt.' }
    if (-not (Test-Path -LiteralPath $Coordinator -PathType Leaf)) { throw 'Aktuelles Startprogramm fehlt.' }
    $arguments = @('-u', '-B', $Coordinator)
    if ($CheckOnly) { $arguments += '--check-only' }
    & $Python @arguments
    $exitCode = $LASTEXITCODE
    if ($exitCode -ne 0) { Write-Host 'Der Start ist fehlgeschlagen. Details und Logpfad stehen oben.' -ForegroundColor Red }
} catch {
    Write-Host ('START FEHLGESCHLAGEN: ' + $_.Exception.Message) -ForegroundColor Red
}
$global:LASTEXITCODE = $exitCode
# The Desktop shortcut uses powershell.exe -NoExit; leave its progress visible.
$keepOpen = @([Environment]::GetCommandLineArgs() | ForEach-Object { $_.ToLowerInvariant() }) -contains '-noexit'
if (-not $keepOpen) { exit $exitCode }
