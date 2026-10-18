[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$desktop = [Environment]::GetFolderPath('DesktopDirectory')
$repository = Split-Path -Parent $PSScriptRoot
$wrapper = Join-Path $PSScriptRoot 'Start-NativeVoice.ps1'
$powershell = Join-Path $env:WINDIR 'System32\WindowsPowerShell\v1.0\powershell.exe'
$demoUrl = 'https://soprasteriaassvsdemo14.service-now.com/now/now-assist-with-va/voice-test/8aa131d793f787105c8132d47aba1095'
$webShortcut = Join-Path $desktop 'SCC - ServiceNow Voice Demo.url'
$definitions = @(
    @{ Name = 'SCC - HaloGen Modell'; Action = 'Model' }
    @{ Name = 'SCC - Speech to Text'; Action = 'STT' }
    @{ Name = 'SCC - Text to Speech'; Action = 'TTS' }
    @{ Name = 'SCC - Voice Bridge'; Action = 'Voice' }
    @{ Name = 'SCC - Gateway'; Action = 'Gateway' }
    @{ Name = 'SCC - Alles starten'; Action = 'All' }
    @{ Name = 'SCC - Status'; Action = 'Status' }
)
$shell = $null

try {
    if ([string]::IsNullOrWhiteSpace($desktop) -or -not (Test-Path -LiteralPath $desktop -PathType Container)) {
        throw 'Der Windows-Desktopordner ist nicht verfuegbar.'
    }
    foreach ($requiredFile in @($wrapper, $powershell)) {
        if (-not (Test-Path -LiteralPath $requiredFile -PathType Leaf)) {
            throw "Erforderliche Datei fehlt: $requiredFile"
        }
    }
    $shell = New-Object -ComObject WScript.Shell
    $shortcuts = foreach ($definition in $definitions) {
        $path = Join-Path $desktop ($definition.Name + '.lnk')
        $arguments = '-NoProfile -NoExit -ExecutionPolicy Bypass -File "{0}" -Action {1}' -f $wrapper, $definition.Action
        if (Test-Path -LiteralPath $path) {
            $existing = $shell.CreateShortcut($path)
            if ($existing.TargetPath -ine $powershell -or $existing.Arguments -cne $arguments) {
                throw "Vorhandene fremde Verknuepfung bleibt unveraendert: $path"
            }
        }
        [PSCustomObject]@{ Name = $definition.Name; Path = $path; Arguments = $arguments }
    }
    # Check every collision before writing any shortcut.
    if (Test-Path -LiteralPath $webShortcut) {
        $existingUrl = [IO.File]::ReadAllLines($webShortcut) | Where-Object { $_ -match '^URL=' }
        if (@($existingUrl).Count -ne 1 -or $existingUrl -cne ('URL=' + $demoUrl)) {
            throw "Vorhandene fremde Webverknuepfung bleibt unveraendert: $webShortcut"
        }
    }
    foreach ($definition in $shortcuts) {
        $shortcut = $shell.CreateShortcut($definition.Path)
        $shortcut.TargetPath = $powershell
        $shortcut.Arguments = $definition.Arguments
        $shortcut.WorkingDirectory = $repository
        $shortcut.Description = $definition.Name
        $shortcut.IconLocation = "$powershell,0"
        $shortcut.Save()
        $saved = $shell.CreateShortcut($definition.Path)
        if ($saved.TargetPath -ine $powershell -or $saved.Arguments -cne $definition.Arguments -or $saved.WorkingDirectory -ine $repository) {
            throw "Pruefung der gespeicherten Verknuepfung fehlgeschlagen: $($definition.Path)"
        }
        Write-Output ("Installiert: {0} -> {1} {2}" -f $definition.Name, $saved.TargetPath, $saved.Arguments)
    }
    [IO.File]::WriteAllText($webShortcut, "[InternetShortcut]`r`nURL=$demoUrl`r`n", [Text.Encoding]::ASCII)
    if ([IO.File]::ReadAllText($webShortcut) -cne "[InternetShortcut]`r`nURL=$demoUrl`r`n") {
        throw "Pruefung der gespeicherten Webverknuepfung fehlgeschlagen: $webShortcut"
    }
    Write-Output "Installiert: SCC - ServiceNow Voice Demo -> $demoUrl"
    Write-Output "Fertig. Verknuepfungen liegen auf: $desktop"
}
catch {
    Write-Host "Installation fehlgeschlagen: $($_.Exception.Message)" -ForegroundColor Red
    exit 1
}
finally {
    if ($null -ne $shell) {
        [void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($shell)
    }
}
