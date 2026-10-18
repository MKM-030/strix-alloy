[CmdletBinding()]
param()
$ErrorActionPreference = 'Stop'
$voiceRoot = Split-Path -Parent $PSScriptRoot
$launcher = Join-Path $voiceRoot 'Start-VoiceStudio.ps1'
if (!(Test-Path -LiteralPath $launcher)) { throw 'Start-VoiceStudio.ps1 fehlt.' }
$shell = New-Object -ComObject WScript.Shell
$powershell = Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\powershell.exe'
$desktop = [Environment]::GetFolderPath('Desktop')
$startup = [Environment]::GetFolderPath('Startup')
foreach ($entry in @(
    @{Path=(Join-Path $desktop 'SCC - Stimmen verwalten.lnk'); Action='Open'},
    @{Path=(Join-Path $startup 'SCC Voice Studio.lnk'); Action='Start'}
)) {
    $link = $shell.CreateShortcut($entry.Path)
    $link.TargetPath = $powershell
    $link.Arguments = '-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File "' + $launcher + '" -Action ' + $entry.Action
    $link.WorkingDirectory = Split-Path -Parent $voiceRoot
    $link.Description = 'Stimmen für die ServiceNow-Sprachdemo aufnehmen und auswählen'
    $link.IconLocation = $powershell + ',0'
    $link.Save()
    Write-Host ('Verknüpfung angelegt: ' + $entry.Path)
}
