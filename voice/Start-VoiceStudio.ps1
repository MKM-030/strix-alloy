[CmdletBinding()]
param(
    [ValidateSet('Start', 'Status', 'Open')][string]$Action = 'Open',
    [string]$Origin = $env:SCC_VOICE_STUDIO_ORIGIN,
    [string]$PythonExecutable = $env:SCC_VOICE_PYTHON
)

$ErrorActionPreference = 'Stop'
$python = $PythonExecutable
if ([string]::IsNullOrWhiteSpace($python)) {
    $python = Join-Path $PSScriptRoot 'native-bridge\.venv\Scripts\python.exe'
}
$launcher = Join-Path $PSScriptRoot 'voice-studio\launch_studio.py'
$accessFile = Join-Path ([Environment]::GetFolderPath('Desktop')) 'Voice-Studio-Zugang.txt'

try {
    if ([string]::IsNullOrWhiteSpace($Origin)) {
        throw 'Set -Origin or SCC_VOICE_STUDIO_ORIGIN to the configured HTTPS origin.'
    }
    if (!(Test-Path -LiteralPath $python -PathType Leaf) -or !(Test-Path -LiteralPath $launcher -PathType Leaf)) {
        throw 'Voice Studio oder die Python-Umgebung fehlt.'
    }
    $operation = if ($Action -eq 'Status') { 'status' } else { 'start' }
    $launchOutput = @(& $python -u $launcher $operation --access-file $accessFile --origin $Origin)
    $result = $LASTEXITCODE
    $launchOutput | Write-Output
    if ($result -ne 0) { exit $result }
    # Auth initialization may produce its own receipt. The launcher result is last.
    $studio = $launchOutput[-1] | ConvertFrom-Json
    if (!$studio.ok -or !$studio.url) { throw 'Voice Studio hat keinen gueltigen Startstatus geliefert.' }
    if ($Action -eq 'Open') {
        Start-Process -FilePath $studio.url
        Write-Host "Zugangscode: $accessFile" -ForegroundColor Cyan
    }
}
catch {
    Write-Host "Voice Studio: $($_.Exception.Message)" -ForegroundColor Red
    exit 1
}
