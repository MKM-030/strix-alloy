Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
if (-not ('SccVoiceRecorder.WindowsMicrophone' -as [type])) {
    Add-Type -Path (Join-Path $PSScriptRoot 'WindowsMicrophone.cs')
}
function Get-VoiceInputDevice {
    [SccVoiceRecorder.WindowsMicrophone]::GetDevices()
}
function Test-RecordedReference {
    param([Parameter(Mandatory = $true)][string]$Path)
    try {
        $analysis = [SccVoiceRecorder.WindowsMicrophone]::AnalyzeWav($Path)
        $reason = ''
        if ($analysis.DurationSeconds -lt 15 -or $analysis.DurationSeconds -gt 30.1) {
            $reason = 'Bitte 15 bis 30 Sekunden aufnehmen.'
        } elseif ($analysis.Rms -lt 0.008 -or $analysis.Peak -lt 0.035) {
            $reason = 'Aufnahme zu leise oder ohne Sprache. Mikrofon und Windows-Eingangspegel pruefen.'
        } elseif ($analysis.ClippedFraction -gt 0.005) {
            $reason = 'Aufnahme uebersteuert. Mikrofonpegel senken oder Abstand vergroessern.'
        }
        [PSCustomObject]@{ Valid = [string]::IsNullOrEmpty($reason); Reason = $reason; Analysis = $analysis }
    } catch {
        [PSCustomObject]@{ Valid = $false; Reason = $_.Exception.Message; Analysis = $null }
    }
}
function New-VoiceActivationRequest {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [Parameter(Mandatory = $true)][string]$Transcript,
        [Parameter(Mandatory = $true)][string]$Name
    )
    if ([string]::IsNullOrWhiteSpace($Transcript)) { throw 'Der genaue gesprochene Text fehlt.' }
    if ([string]::IsNullOrWhiteSpace($Name)) { throw 'Der Profilname fehlt.' }
    $validation = Test-RecordedReference $Path
    if (-not $validation.Valid) { throw $validation.Reason }
    @{
        wav_path = [IO.Path]::GetFullPath($Path)
        reference_text = $Transcript.Trim()
        name = $Name.Trim()
        language = 'German'
        source = 'desktop_microphone'
        consent = @{
            own_voice = $true
            confirmed_at_utc = [DateTime]::UtcNow.ToString('o')
            scope = 'local_synthetic_voice_and_servicenow_demo'
        }
    }
}
function Invoke-VoiceProfileActivation {
    param(
        [Parameter(Mandatory = $true)][string]$PythonExecutable,
        [Parameter(Mandatory = $true)][string]$HelperPath,
        [Parameter(Mandatory = $true)][string]$RequestPath,
        [ValidateRange(1, 600)][int]$TimeoutSeconds = 300
    )
    foreach ($path in @($PythonExecutable, $HelperPath, $RequestPath)) {
        if (-not (Test-Path -LiteralPath $path -PathType Leaf)) { throw "Erforderliche Datei fehlt: $path" }
        if ($path.Contains('"')) { throw 'Ungueltiger Dateipfad.' }
    }
    $start = New-Object Diagnostics.ProcessStartInfo
    $start.FileName = $PythonExecutable
    $start.Arguments = '"{0}" activate --request "{1}" --json' -f $HelperPath, $RequestPath
    $start.UseShellExecute = $false
    $start.CreateNoWindow = $true
    $start.RedirectStandardOutput = $true
    $start.RedirectStandardError = $true
    $start.StandardOutputEncoding = New-Object Text.UTF8Encoding($false)
    $start.StandardErrorEncoding = New-Object Text.UTF8Encoding($false)
    $start.EnvironmentVariables['PYTHONUTF8'] = '1'
    $process = New-Object Diagnostics.Process
    $process.StartInfo = $start
    try {
        if (-not $process.Start()) { throw 'Aktivierungsprozess konnte nicht gestartet werden.' }
        $outputTask = $process.StandardOutput.ReadToEndAsync()
        $errorTask = $process.StandardError.ReadToEndAsync()
        if (-not $process.WaitForExit($TimeoutSeconds * 1000)) {
            $process.Kill()
            [void]$process.WaitForExit(5000)
            throw 'Aktivierung hat das Zeitlimit erreicht. Sprachstatus pruefen, bevor die Demo fortgesetzt wird.'
        }
        $stdout = $outputTask.GetAwaiter().GetResult()
        $stderr = $errorTask.GetAwaiter().GetResult()
        try { $result = $stdout | ConvertFrom-Json -ErrorAction Stop }
        catch { throw ("Aktivierung lieferte keine gueltige Antwort. {0}" -f $stderr.Trim()) }
        if ($process.ExitCode -ne 0 -or $null -eq $result -or -not $result.ok) {
            $message = if ($null -ne $result -and $result.PSObject.Properties['error']) { $result.error } else { $stderr.Trim() }
            throw ("Aktivierung fehlgeschlagen: {0}" -f $message)
        }
        if ($result.active_voice -cne 'scc-demo' -or [string]::IsNullOrWhiteSpace($result.profile_id)) {
            throw 'Aktivierung bestaetigte nicht das SCC-Sprachprofil. Sprachstatus pruefen.'
        }
        $result
    } finally { $process.Dispose() }
}
Export-ModuleMember -Function Get-VoiceInputDevice, Test-RecordedReference, New-VoiceActivationRequest, Invoke-VoiceProfileActivation
