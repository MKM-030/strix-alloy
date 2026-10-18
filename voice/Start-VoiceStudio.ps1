[CmdletBinding()]
param([ValidateSet('Start', 'Status', 'Open')][string]$Action = 'Open')

$ErrorActionPreference = 'Stop'
$python = Join-Path $PSScriptRoot 'native-bridge\.venv\Scripts\python.exe'
$launcher = Join-Path $PSScriptRoot 'voice-studio\launch_studio.py'
$accessFile = Join-Path ([Environment]::GetFolderPath('Desktop')) 'Voice-Studio-Zugang.txt'
$url = 'https://strix-alloy.tail7f425a.ts.net/voice-studio/'

try {
    if (!(Test-Path -LiteralPath $python) -or !(Test-Path -LiteralPath $launcher)) {
        throw 'Voice Studio oder die Python-Umgebung fehlt.'
    }
    $operation = if ($Action -eq 'Status') { 'status' } else { 'start' }
    & $python -u $launcher $operation --access-file $accessFile
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    if ($Action -eq 'Open') {
        Start-Process $url
        Write-Host "Zugangscode: $accessFile" -ForegroundColor Cyan
    }
}
catch {
    Write-Host "Voice Studio: $($_.Exception.Message)" -ForegroundColor Red
    exit 1
}
