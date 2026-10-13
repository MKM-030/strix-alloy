[CmdletBinding()]
param([string]$RecorderDirectory = $PSScriptRoot)
$ErrorActionPreference = 'Stop'
$failed = 0
function Check([string]$Name, [scriptblock]$Body) {
    try { & $Body; Write-Output "PASS $Name" }
    catch { $script:failed++; Write-Output "FAIL $Name : $($_.Exception.Message)" }
}
function Assert([bool]$Condition, [string]$Message) { if (-not $Condition) { throw $Message } }
function Write-Fixture([string]$Path, [double]$Seconds, [double]$Amplitude, [bool]$Stereo = $false, [double]$ClippedFraction = 0) {
    $rate = 24000
    $channels = if ($Stereo) { 2 } else { 1 }
    $samples = [int]($rate * $Seconds)
    $writer = New-Object IO.BinaryWriter([IO.File]::Create($Path))
    try {
        $writer.Write([Text.Encoding]::ASCII.GetBytes('RIFF')); $writer.Write([uint32](36 + $samples * 2 * $channels))
        $writer.Write([Text.Encoding]::ASCII.GetBytes('WAVEfmt ')); $writer.Write([uint32]16)
        $writer.Write([uint16]1); $writer.Write([uint16]$channels); $writer.Write([uint32]$rate)
        $writer.Write([uint32]($rate * 2 * $channels)); $writer.Write([uint16](2 * $channels)); $writer.Write([uint16]16)
        $writer.Write([Text.Encoding]::ASCII.GetBytes('data')); $writer.Write([uint32]($samples * 2 * $channels))
        for ($i = 0; $i -lt $samples; $i++) {
            $value = [int16]([Math]::Sin(2 * [Math]::PI * 190 * $i / $rate) * $Amplitude * 32767)
            if (($i % 1000) -lt [int]($ClippedFraction * 1000)) { $value = [int16]32700 }
            for ($channel = 0; $channel -lt $channels; $channel++) { $writer.Write($value) }
        }
    } finally { $writer.Dispose() }
}
$temporary = Join-Path ([IO.Path]::GetTempPath()) ('scc-recorder-test-' + [guid]::NewGuid().ToString('N'))
[void][IO.Directory]::CreateDirectory($temporary)
try {
    Check 'recorder safety functions are available' {
        $module = Join-Path $RecorderDirectory 'VoiceRecorder.psm1'
        Assert (Test-Path -LiteralPath $module) 'VoiceRecorder module is not implemented yet'
        Import-Module $module -Force
        Assert ($null -ne (Get-Command Test-RecordedReference -ErrorAction SilentlyContinue)) 'Missing recording validation'
    }
    if ($failed -eq 0) {
        Write-Fixture (Join-Path $temporary 'good.wav') 20 0.20
        Write-Fixture (Join-Path $temporary 'silence.wav') 20 0
        Write-Fixture (Join-Path $temporary 'short.wav') 3 0.20
        Write-Fixture (Join-Path $temporary 'stereo.wav') 20 0.20 $true
        Write-Fixture (Join-Path $temporary 'clipped.wav') 20 1.0
        Write-Fixture (Join-Path $temporary 'marginal-clipping.wav') 20 0.20 $false 0.006
        Check 'spoken-level reference passes and reports exact duration' {
            $result = Test-RecordedReference (Join-Path $temporary 'good.wav')
            Assert $result.Valid 'Valid 20-second reference was rejected'
            Assert ([Math]::Abs($result.Analysis.DurationSeconds - 20) -lt 0.001) 'Incorrect WAV duration'
        }
        Check 'silence is rejected' {
            $result = Test-RecordedReference (Join-Path $temporary 'silence.wav')
            Assert (-not $result.Valid) 'Silent recording must not be activated'
            Assert ($result.Reason -match 'leise|Sprache') 'Silence rejection should guide the operator'
        }
        Check 'short reference is rejected' {
            $result = Test-RecordedReference (Join-Path $temporary 'short.wav')
            Assert (-not $result.Valid) 'Three-second recording must not be activated'
        }
        Check 'stereo is rejected' {
            $result = Test-RecordedReference (Join-Path $temporary 'stereo.wav')
            Assert (-not $result.Valid) 'Unexpected WAV format must not be activated'
        }
        Check 'excessive clipping is rejected' {
            $result = Test-RecordedReference (Join-Path $temporary 'clipped.wav')
            Assert (-not $result.Valid) 'Clipped recording must not be activated'
        }
        Check 'clipping over the activation helper limit is rejected before confirmation' {
            $result = Test-RecordedReference (Join-Path $temporary 'marginal-clipping.wav')
            Assert (-not $result.Valid) '0.6 percent samples at 32700 must be rejected like the activation helper'
        }
        Check 'truncated WAV is rejected' {
            [IO.File]::WriteAllBytes((Join-Path $temporary 'bad.wav'), [Text.Encoding]::ASCII.GetBytes('RIFF'))
            $result = Test-RecordedReference (Join-Path $temporary 'bad.wav')
            Assert (-not $result.Valid) 'Invalid WAV must not be activated'
        }
        Check 'consent request contains the recorded transcript and scope' {
            $request = New-VoiceActivationRequest (Join-Path $temporary 'good.wav') 'Meine eigene Stimme.' 'Testprofil'
            Assert ($request.consent.own_voice -eq $true) 'Own-voice confirmation missing'
            Assert ($request.consent.scope -ceq 'local_synthetic_voice_and_servicenow_demo') 'Consent scope changed'
            Assert ($request.reference_text -ceq 'Meine eigene Stimme.') 'Transcript changed'
            Assert ($request.source -ceq 'desktop_microphone') 'Recording provenance missing'
        }
        Check 'empty transcript cannot create an activation request' {
            $rejected = $false
            try { $null = New-VoiceActivationRequest (Join-Path $temporary 'good.wav') ' ' 'Testprofil' }
            catch { $rejected = $true }
            Assert $rejected 'Empty transcript was accepted'
        }
        Check 'Windows microphone inventory can be read without capture' {
            $devices = @(Get-VoiceInputDevice)
            Assert ($devices.Count -gt 0) 'No Windows audio input device is available'
            $devices | ForEach-Object { Write-Output ("DEVICE {0}: {1}" -f $_.Id, $_.Name) }
        }
        $python = (Get-Command python -ErrorAction Stop).Source
        $requestPath = Join-Path $temporary 'request.json'
        [IO.File]::WriteAllText($requestPath, '{}')
        $helper = Join-Path $temporary 'activation-fixture.py'
        Check 'activation recognizes confirmed service response' {
            [IO.File]::WriteAllText($helper, 'print(''{"ok":true,"active_voice":"scc-demo","profile_id":"fixture"}'')')
            $result = Invoke-VoiceProfileActivation $python $helper $requestPath
            Assert ($result.profile_id -ceq 'fixture') 'Activation result was not returned'
        }
        Check 'activation failure cannot be presented as success' {
            [IO.File]::WriteAllText($helper, 'import sys; print(''{"ok":false,"error":"fixture rejected"}''); sys.exit(1)')
            $rejected = $false
            try { $null = Invoke-VoiceProfileActivation $python $helper $requestPath }
            catch { $rejected = $_.Exception.Message -match 'fixture rejected' }
            Assert $rejected 'Rejected activation was not surfaced'
        }
        Check 'hung activation process is bounded and terminated' {
            [IO.File]::WriteAllText($helper, 'import time; time.sleep(20)')
            $clock = [Diagnostics.Stopwatch]::StartNew()
            $rejected = $false
            try { $null = Invoke-VoiceProfileActivation $python $helper $requestPath -TimeoutSeconds 1 }
            catch { $rejected = $_.Exception.Message -match 'Zeitlimit' }
            Assert $rejected 'Hung activation was not rejected'
            Assert ($clock.Elapsed.TotalSeconds -lt 8) 'Activation timeout was not bounded'
        }
    }
} finally {
    Remove-Item -LiteralPath $temporary -Recurse -Force -ErrorAction SilentlyContinue
}
if ($failed -gt 0) { throw "$failed recorder tests failed" }
Write-Output 'All recorder tests passed; no microphone recording or synthesis was performed.'
