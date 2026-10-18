[CmdletBinding()]
param(
    [ValidateRange(15, 30)][int]$DurationSeconds = 25,
    [int]$DeviceId = -2,
    [string]$PythonExecutable,
    [switch]$Check,
    [switch]$ListDevices
)
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
Import-Module (Join-Path $PSScriptRoot 'VoiceRecorder.psm1') -Force
$helper = Join-Path $PSScriptRoot 'manage_voice.py'
$referenceText = 'Guten Tag, ich helfe Ihnen bei der Einrichtung Ihres neuen Laptops. Wir pruefen zuerst die Anmeldung und richten danach Ihre Arbeitsumgebung ein. Dabei erklaere ich jeden Schritt ruhig und klar. Wenn etwas nicht funktioniert, finden wir gemeinsam eine Loesung. Am Ende pruefen wir, ob alle Programme und Zubehoer fuer Ihre Arbeit bereitstehen.'
$referenceText = $referenceText.Replace('pruefen', ('pr' + [char]0x00FC + 'fen')).Replace('erklaere', ('erkl' + [char]0x00E4 + 're')).Replace('Loesung', ('L' + [char]0x00F6 + 'sung')).Replace('Zubehoer', ('Zubeh' + [char]0x00F6 + 'r')).Replace('fuer', ('f' + [char]0x00FC + 'r'))
function Resolve-Python {
    if (-not [string]::IsNullOrWhiteSpace($PythonExecutable)) { return $PythonExecutable }
    # The existing startup/ASR environment includes psutil, required by the
    # activation helper's native-service ownership check.
    $startupPython = 'E:\SCC-Voice\asr-env\Scripts\python.exe'
    if (Test-Path -LiteralPath $startupPython -PathType Leaf) { return $startupPython }
    $bridgePython = Join-Path (Split-Path -Parent $PSScriptRoot) 'native-bridge\.venv\Scripts\python.exe'
    if (Test-Path -LiteralPath $bridgePython -PathType Leaf) { return $bridgePython }
    $command = Get-Command python -ErrorAction SilentlyContinue
    if ($null -eq $command) { throw 'Python wurde nicht gefunden. -PythonExecutable mit dem Python-Pfad verwenden.' }
    return $command.Source
}
try {
    $devices = @(Get-VoiceInputDevice)
    if ($ListDevices) { $devices | Format-Table Id, Name -AutoSize; return }
    $python = Resolve-Python
    if ($devices.Count -eq 0) { throw 'Kein Mikrofon gefunden. Mikrofon anschliessen und Windows-Eingabe pruefen.' }
    if (-not (Test-Path -LiteralPath $helper -PathType Leaf)) { throw "Sprachprofil-Helfer fehlt: $helper" }
    if ($Check) {
        Write-Output 'Recorder und Windows-Audio-Code geladen. Keine Aufnahme gestartet.'
        Write-Output "Python: $python"
        Write-Output "Aktivierungshelfer: $helper"
        foreach ($device in $devices) {
            Write-Output ("Mikrofon {0}: {1}; PCM24k unterstuetzt: {2}" -f $device.Id, $device.Name, [SccVoiceRecorder.WindowsMicrophone]::SupportsFormat($device.Id))
        }
        return
    }
    if ([Console]::IsInputRedirected) { throw 'Dieses Werkzeug braucht ein interaktives Fenster. Desktop-Verknuepfung oeffnen.' }
    Write-Host ''
    Write-Host 'SCC - Eigene Stimme aufnehmen' -ForegroundColor Cyan
    Write-Host 'Ihre Aufnahme wird lokal als synthetische Stimme fuer die ServiceNow-Demo verwendet.'
    Write-Host 'Sprechen Sie selbst. Starten Sie Aufnahme und Aktivierung zwischen Demo-Anrufen.'
    Write-Host 'Windows: Einstellungen > Datenschutz und Sicherheit > Mikrofon > Desktop-Apps zulassen.'
    Write-Host ''
    if ((Read-Host 'Ich nehme meine eigene Stimme auf und stimme dieser Nutzung zu. JA eingeben') -cne 'JA') {
        Write-Host 'Abgebrochen. Es wurde keine Aufnahme gestartet.'; return
    }
    $devices | Format-Table Id, Name -AutoSize | Out-Host
    if ($DeviceId -eq -2) {
        $choice = Read-Host 'Mikrofon-ID eingeben (Enter = Windows-Standardmikrofon)'
        if ([string]::IsNullOrWhiteSpace($choice)) { $DeviceId = -1 }
        else {
            $parsed = 0
            if (-not [int]::TryParse($choice, [ref]$parsed)) { throw 'Bitte eine angezeigte Mikrofon-ID eingeben.' }
            $DeviceId = $parsed
        }
    }
    if ($DeviceId -ne -1 -and -not ($devices.Id -contains $DeviceId)) { throw 'Die Mikrofon-ID ist nicht vorhanden.' }
    if (-not [SccVoiceRecorder.WindowsMicrophone]::SupportsFormat($DeviceId)) { throw 'Das Mikrofon unterstuetzt PCM24k nicht. Anderes Mikrofon auswaehlen.' }
    $name = Read-Host 'Profilname (Enter = Meine Stimme)'
    if ([string]::IsNullOrWhiteSpace($name)) { $name = 'Meine Stimme' }
    $root = Join-Path $PSScriptRoot 'runtime'
    while ($true) {
        Write-Host ''
        Write-Host "Lesen Sie diesen Text natuerlich und deutlich in etwa $DurationSeconds Sekunden:" -ForegroundColor Cyan
        Write-Host $referenceText
        Write-Host 'Kleine Pausen sind gut. Ruhiger Raum, etwa 20 cm Abstand; nicht fluestern.'
        if ((Read-Host 'Enter startet die Aufnahme; A bricht ab') -match '^(a|abbrechen)$') { return }
        $folder = Join-Path $root ([DateTime]::UtcNow.ToString('yyyyMMddTHHmmssZ') + '-' + [guid]::NewGuid().ToString('N'))
        [void][IO.Directory]::CreateDirectory($folder)
        $wav = Join-Path $folder 'reference.wav'
        Write-Host 'Aufnahme startet in 3 Sekunden ...' -ForegroundColor Yellow
        for ($countdown = 3; $countdown -gt 0; $countdown--) { Write-Host $countdown; Start-Sleep -Seconds 1 }
        [SccVoiceRecorder.WindowsMicrophone]::Capture($wav, $DeviceId, $DurationSeconds)
        $validation = Test-RecordedReference $wav
        if (-not $validation.Valid) {
            Write-Host $validation.Reason -ForegroundColor Yellow
            Remove-Item -LiteralPath $folder -Recurse -Force
            if ((Read-Host 'R = erneut aufnehmen; Enter = abbrechen') -match '^(r|erneut)$') { continue }
            return
        }
        Write-Host ("Aufnahme geprueft: {0:N1} s; Pegel {1:N3}." -f $validation.Analysis.DurationSeconds, $validation.Analysis.Rms)
        Write-Host 'Die Aufnahme wird jetzt zur Kontrolle abgespielt.'
        $player = New-Object Media.SoundPlayer($wav)
        try { $player.Load(); $player.PlaySync() } finally { $player.Dispose() }
        while ($true) {
            $action = Read-Host 'Enter = weiter; P = noch einmal abspielen; R = neu aufnehmen; A = abbrechen'
            if ($action -match '^(p|play)$') {
                $player = New-Object Media.SoundPlayer($wav)
                try { $player.Load(); $player.PlaySync() } finally { $player.Dispose() }
                continue
            }
            break
        }
        if ($action -match '^(r|erneut)$') { Remove-Item -LiteralPath $folder -Recurse -Force; continue }
        if ($action -match '^(a|abbrechen)$') { Remove-Item -LiteralPath $folder -Recurse -Force; return }
        $transcript = Read-Host 'Falls Sie anders gesprochen haben, genauen Wortlaut eingeben (Enter = angezeigter Text)'
        if ([string]::IsNullOrWhiteSpace($transcript)) { $transcript = $referenceText }
        Write-Host ''
        Write-Host "Profil: $name"
        Write-Host "Gesprochener Text: $transcript"
        Write-Host 'Aktivierung ersetzt die Stimme fuer den naechsten SCC-Demo-Anruf.' -ForegroundColor Yellow
        if ((Read-Host 'Kein Anruf aktiv, Aufnahme gehoert und Text korrekt? AKTIVIEREN eingeben') -cne 'AKTIVIEREN') {
            Remove-Item -LiteralPath $folder -Recurse -Force
            Write-Host 'Abgebrochen. Das bisherige Sprachprofil bleibt unveraendert.'; return
        }
        $request = New-VoiceActivationRequest $wav $transcript $name
        $requestPath = Join-Path $folder 'request.json'
        [IO.File]::WriteAllText($requestPath, ($request | ConvertTo-Json -Depth 5), (New-Object Text.UTF8Encoding($false)))
        Write-Host 'Sprachprofil wird geprueft und aktiviert. Das kann etwas dauern ...' -ForegroundColor Cyan
        $activated = Invoke-VoiceProfileActivation $python $helper $requestPath
        Write-Host ("Aktiv: {0} ({1}). Der naechste ServiceNow-Anruf nutzt Ihre Stimme." -f $name, $activated.profile_id) -ForegroundColor Green
        Write-Host "Aufnahme: $wav"
        return
    }
} catch {
    Write-Host ("Fehler: {0}" -f $_.Exception.Message) -ForegroundColor Red
    Write-Host 'Keine erfolgreiche Aktivierung bestaetigt. Bei Aktivierungsfehler den Sprachstatus pruefen.'
    exit 1
}
