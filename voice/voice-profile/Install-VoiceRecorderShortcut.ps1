[CmdletBinding()]
param()
$ErrorActionPreference = 'Stop'
$script = Join-Path $PSScriptRoot 'Record-OwnVoice.ps1'
$repository = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$desktop = [Environment]::GetFolderPath('DesktopDirectory')
$powershell = Join-Path $env:WINDIR 'System32\WindowsPowerShell\v1.0\powershell.exe'
$shortcutPath = Join-Path $desktop 'SCC - Eigene Stimme aufnehmen.lnk'
$arguments = '-NoProfile -NoExit -ExecutionPolicy Bypass -File "{0}"' -f $script
$shell = $null
try {
    foreach ($required in @($script, $powershell)) {
        if (-not (Test-Path -LiteralPath $required -PathType Leaf)) { throw "Datei fehlt: $required" }
    }
    if (-not (Test-Path -LiteralPath $desktop -PathType Container)) { throw 'Windows-Desktopordner fehlt.' }
    $shell = New-Object -ComObject WScript.Shell
    if (Test-Path -LiteralPath $shortcutPath) {
        $existing = $shell.CreateShortcut($shortcutPath)
        if ($existing.TargetPath -ine $powershell -or $existing.Arguments -cne $arguments) {
            throw "Vorhandene fremde Verknuepfung bleibt unveraendert: $shortcutPath"
        }
    }
    $shortcut = $shell.CreateShortcut($shortcutPath)
    $shortcut.TargetPath = $powershell
    $shortcut.Arguments = $arguments
    $shortcut.WorkingDirectory = $repository
    $shortcut.Description = 'Eigene Mikrofonstimme aufnehmen, anhoeren und fuer die SCC-Demo aktivieren'
    $shortcut.IconLocation = "$powershell,0"
    $shortcut.Save()
    $saved = $shell.CreateShortcut($shortcutPath)
    if ($saved.TargetPath -ine $powershell -or $saved.Arguments -cne $arguments -or $saved.WorkingDirectory -ine $repository) {
        throw 'Pruefung der gespeicherten Verknuepfung fehlgeschlagen.'
    }
    Write-Output "Installiert: $shortcutPath"
    Write-Output ("Ziel: {0} {1}" -f $saved.TargetPath, $saved.Arguments)
} finally {
    if ($null -ne $shell) { [void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($shell) }
}
