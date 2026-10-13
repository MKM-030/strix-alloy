[CmdletBinding()]
param(
    [ValidateSet('Start', 'Status')]
    [string]$Action = 'Status'
)

# Starts only the existing managed HaloGen profile. The single reviewed failed
# incident may be archived after the requested restart gate and proven cleanup; existing processes are never stopped.
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$Clean = 'C:\Projects\strix-alloy-clean'
$Python = "$Clean\server\.local\venv\Scripts\python.exe"
$Controller = "$Clean\server\controller.py"
$Profile = "$Clean\server\.local\optimization9h-20261004\halogen0172-backend-preparation-20261008\halogen0181-version-bracket-20261012\serving0181-full262-exact-cache-candidate-20261013.json"
$ProfileHash = 'f62b654bd0cfd0bcd00b4ced7416b64584ca530e6be8120e5d61dc45b931c323'
$StatePath = "$Clean\server\.local\current.json"
$RunnerLock = "$Clean\backends\halogen-wsl2-0.18.1\.local\runner.lock"
$StatusScript = Join-Path $PSScriptRoot 'native-speech-validation\stack_status.py'
$Runtime = Join-Path $PSScriptRoot 'native-speech-validation\runtime'
$AdmissionScript = Join-Path $PSScriptRoot 'native-start\model_admission.py'
$StartPolicy = Join-Path $PSScriptRoot 'native-start\model-start-policy.json'
$AdmissionHash = 'a14f0ec5894464ce46daf9f7adaf3b725111dddc4981a27e9dd3b6450c7e48a1'
$StartPolicyHash = '1a9e2392f765f800bb6e23f596d41db8fbe0b02d798c1050d328b5d975408e25'
$mutex = $null
$acquired = $false

function Read-ControllerState {
    if (-not (Test-Path -LiteralPath $StatePath -PathType Leaf)) { return $null }
    try {
        $value = Get-Content -LiteralPath $StatePath -Raw -Encoding UTF8 | ConvertFrom-Json
        if ($value -isnot [pscustomobject]) { throw 'invalid object' }
        foreach ($field in @('phase', 'run_id', 'pid', 'profile_sha256', 'heartbeat')) {
            if ($field -notin @($value.PSObject.Properties.Name)) { throw 'missing field' }
        }
        if (($value.heartbeat -isnot [double] -and $value.heartbeat -isnot [decimal] -and
             $value.heartbeat -isnot [long] -and $value.heartbeat -isnot [int]) -or
            [double]::IsNaN([double]$value.heartbeat) -or [double]::IsInfinity([double]$value.heartbeat)) {
            throw 'invalid heartbeat'
        }
        if ($value.phase -notin @('starting', 'ready', 'stopping', 'stopped', 'failed') -or
            $value.run_id -notmatch '^[0-9a-f]{32}$' -or $value.profile_sha256 -notmatch '^[0-9a-f]{64}$' -or
            [int]$value.pid -le 0 -or [double]$value.heartbeat -le 0) { throw 'invalid metadata' }
        return $value
    }
    catch { throw 'HaloGen: Controller-Metadaten sind unlesbar; kein Start.' }
}

function Test-CommandArgument([string]$CommandLine, [string]$Value) {
    $escaped = [regex]::Escape($Value)
    return [regex]::IsMatch($CommandLine, '(?:^|\s)(?:"' + $escaped + '"|' + $escaped + ')(?=\s|$)', [Text.RegularExpressions.RegexOptions]::IgnoreCase)
}

function Get-ModelProcesses {
    # Compare the complete managed script path, never adopt a process by name/PID alone.
    return @(Get-CimInstance Win32_Process | Where-Object {
        $_.Name -match '^python(w)?\.exe$' -and $_.CommandLine -and
        (Test-CommandArgument $_.CommandLine $Controller)
    })
}

function Test-OwnedController($State, $Processes) {
    if ($null -eq $State -or $State.profile_sha256 -ne $ProfileHash -or
        $State.phase -notin @('starting', 'ready')) { return $false }
    $matching = @($Processes | Where-Object {
        $_.ProcessId -eq [int]$State.pid -and
        (Test-CommandArgument $_.CommandLine $Profile) -and
        $_.CommandLine -match '(?:^|\s)run(?:\s|$)' -and
        ($_.CommandLine -notmatch '--port(?:\s|=)' -or $_.CommandLine -match '--port\s+8840(?:\s|$)')
    })
    if ($matching.Count -ne 1) { return $false }
    $age = [DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds()/1000.0 - [double]$State.heartbeat
    if ($age -lt 0 -or $age -gt 15) { return $false }
    $createdUtc = $matching[0].CreationDate.ToUniversalTime()
    $created = ([DateTimeOffset]$createdUtc).ToUnixTimeMilliseconds()/1000.0
    if ($created -gt [double]$State.heartbeat) { return $false }
    $allowed = @($Python)
    $venvConfig = "$Clean\server\.local\venv\pyvenv.cfg"
    if (Test-Path -LiteralPath $venvConfig) {
        $homeLine = Get-Content -LiteralPath $venvConfig | Where-Object { $_ -match '^home\s*=\s*(.+)$' } | Select-Object -First 1
        if ($homeLine -match '^home\s*=\s*(.+)$') { $allowed += (Join-Path ($Matches[1].Trim()) 'python.exe') }
    }
    if ($matching[0].ExecutablePath -notin $allowed) { return $false }
    # The venv launcher can be the actual worker's parent. Only its verified
    # ancestor chain is allowed; a second unrelated controller is rejected.
    $lineage = @([int]$matching[0].ProcessId)
    $child = $matching[0]
    for ($depth = 0; $depth -lt 8; $depth++) {
        $parents = @($Processes | Where-Object { $_.ProcessId -eq $child.ParentProcessId })
        if ($parents.Count -eq 0) { break }
        if ($parents.Count -ne 1) { return $false }
        $parent = $parents[0]
        if ($parent.ProcessId -in $lineage -or $parent.ExecutablePath -notin $allowed -or
            -not (Test-CommandArgument $parent.CommandLine $Profile) -or
            $parent.CreationDate -gt $child.CreationDate) { return $false }
        $lineage += [int]$parent.ProcessId
        $child = $parent
    }
    return @($Processes | Where-Object { [int]$_.ProcessId -notin $lineage }).Count -eq 0
}

function Test-ExactCacheHealth($Cache) {
    if ($null -eq $Cache) { return $false }
    foreach ($field in @('mode', 'enabled', 'cap_mb', 'bitwise_identical_to_cold')) {
        if ($field -notin @($Cache.PSObject.Properties.Name)) { return $false }
    }
    if ($Cache.mode -isnot [int] -or $Cache.enabled -isnot [bool] -or
        ($Cache.cap_mb -isnot [int] -and $Cache.cap_mb -isnot [long]) -or
        $Cache.bitwise_identical_to_cold -isnot [bool]) { return $false }
    return $Cache.mode -eq 1 -and $Cache.enabled -eq $true -and
        $Cache.cap_mb -gt 0 -and $Cache.bitwise_identical_to_cold -eq $true
}

function Get-ListenerSnapshot {
    return @(Get-NetTCPConnection -State Listen -ErrorAction Stop | Where-Object {
        $_.LocalPort -in @(8731, 8840, 8851, 8852)
    })
}

try {
    foreach ($file in @($Python, $Controller, $Profile, $StatusScript, $AdmissionScript, $StartPolicy)) {
        if (-not (Test-Path -LiteralPath $file -PathType Leaf)) { throw "HaloGen: Datei fehlt: $file" }
    }
    if ((Get-FileHash -LiteralPath $Profile -Algorithm SHA256).Hash.ToLowerInvariant() -ne $ProfileHash) {
        throw 'HaloGen: Das freigegebene Exact-Cache-Profil wurde veraendert; kein Start.'
    }
    if ((Get-FileHash -LiteralPath $AdmissionScript -Algorithm SHA256).Hash.ToLowerInvariant() -ne $AdmissionHash -or
        (Get-FileHash -LiteralPath $StartPolicy -Algorithm SHA256).Hash.ToLowerInvariant() -ne $StartPolicyHash) {
        throw 'HaloGen: Gepruefte 36-GiB-Startpolitik oder Speichersampler veraendert; kein Start.'
    }
    $admissionPolicy = Get-Content -LiteralPath $StartPolicy -Raw -Encoding UTF8 | ConvertFrom-Json
    if ($Action -eq 'Start') {
        $mutex = New-Object -TypeName System.Threading.Mutex -ArgumentList @($false, 'Local\SCCNativeOriginalModelStarter')
        try { $acquired = $mutex.WaitOne(0) }
        catch [System.Threading.AbandonedMutexException] { $acquired = $true }
        if (-not $acquired) { throw 'HaloGen: Ein anderer Modellstart wird bereits geprueft.' }
    }

    $state = Read-ControllerState
    $processes = @(Get-ModelProcesses)
    $listeners = @(Get-ListenerSnapshot)
    $owned = Test-OwnedController $state $processes
    $phase = if ($null -eq $state) { 'absent' } else { [string]$state.phase }
    $modelListeners = @($listeners | Where-Object { $_.LocalPort -in @(8731, 8840) })
    $legacy = @($listeners | Where-Object { $_.LocalPort -in @(8851, 8852) } | Select-Object -ExpandProperty LocalPort -Unique)
    $health = $null
    $cache = $null
    $cacheMatches = $false
    if ($owned -and $state.phase -eq 'ready') {
        # Existing status helper makes only bounded, allowlisted local GET requests.
        $healthText = & $Python -B $StatusScript
        $health = ($healthText -join [Environment]::NewLine) | ConvertFrom-Json
        if ('prompt_cache' -in @($health.services.model.PSObject.Properties.Name)) {
            $cache = $health.services.model.prompt_cache
        }
        $cacheMatches = Test-ExactCacheHealth $cache
    }

    if ($Action -eq 'Status') {
        [pscustomobject]@{action='status';read_only=$true;phase=$phase;owned_controller=$owned;
            controller_pid=$(if ($owned) {[int]$state.pid} else {$null});runner_lock_exists=(Test-Path -LiteralPath $RunnerLock);
            model_ports=@($modelListeners | Select-Object -ExpandProperty LocalPort -Unique);legacy_ports=$legacy;
            profile_sha256=$ProfileHash;cache_expected='Exact';cache_mode=$(if ($null -ne $cache -and 'mode' -in @($cache.PSObject.Properties.Name)) {$cache.mode} else {$null});
            prompt_cache=$cache;cache_matches=$cacheMatches;start_physical_gib=$admissionPolicy.start_physical_gib;
            terminal_restart_physical_gib=$admissionPolicy.terminal_restart_physical_gib;
            start_commit_headroom_gib=$admissionPolicy.start_commit_headroom_gib;runtime_reserve_gib=18} | ConvertTo-Json -Depth 4
        exit 0
    }
    if ($legacy.Count) { throw 'HaloGen: Legacy-CPU-Audio auf 8851/8852 aktiv. Start-Voice.ps1 nicht verwenden; kein Modellstart.' }
    if ($owned) {
        $controllerListeners = @($modelListeners | Where-Object {$_.LocalPort -eq 8840})
        if ($controllerListeners.Count -gt 1 -or
            ($state.phase -eq 'ready' -and $controllerListeners.Count -ne 1) -or
            ($controllerListeners.Count -eq 1 -and $controllerListeners[0].OwningProcess -ne [int]$state.pid)) {
            throw 'HaloGen: Port 8840 gehoert nicht dem geprueften Controller.'
        }
        if ($state.phase -eq 'ready') {
            if ($health.services.model.http_status -ne 200 -or -not $health.services.model.expected_model -or
                -not $health.services.model.version_matches -or $health.services.model.context -ne 262144 -or
                $health.services.model.slots -ne 1 -or $health.services.controller.http_status -ne 200 -or
                -not $cacheMatches) {
                throw 'HaloGen: Bestehender Controller ist nicht gesund; kein automatischer Neustart.'
            }
        }
        [pscustomobject]@{action='reuse';phase=$state.phase;controller_pid=[int]$state.pid;profile_sha256=$ProfileHash;
            cache_expected='Exact';cache_mode=$(if ($null -ne $cache -and 'mode' -in @($cache.PSObject.Properties.Name)) {$cache.mode} else {$null});
            cache_matches=$cacheMatches} | ConvertTo-Json
        exit 0
    }
    if ($processes.Count -or $modelListeners.Count) { throw 'HaloGen: Bestehender Prozess oder Port ist nicht eindeutig zugeordnet; kein Start.' }
    if (Test-Path -LiteralPath $RunnerLock) {
        # One root-reviewed historical incident only. Every other retained lock fails closed.
        $recovery = Join-Path $PSScriptRoot 'native-start\model_restart_a596d8.py'
        $recoveryHash = '21b38ac5b0e20ad1d7b93eb1164442ae56d338651c5d06419f5ff4475eea54ab'
        if ($null -eq $state -or $state.phase -ne 'failed' -or
            $state.run_id -ne 'ac678e51cef84d819a8fd276dcb93271' -or
            $state.profile_sha256 -ne $ProfileHash -or
            -not (Test-Path -LiteralPath $recovery -PathType Leaf) -or
            (Get-FileHash -LiteralPath $recovery -Algorithm SHA256).Hash.ToLowerInvariant() -ne $recoveryHash) {
            throw 'HaloGen: Schutzsperre nicht dem geprueften terminalen Vorfall zugeordnet; keine automatische Recovery.'
        }
        Write-Host 'HaloGen: prueft dokumentierte Recovery des abgeschlossenen Sicherheitsstopps (angeforderte 36 GiB freier RAM; historische Recovery bleibt fehlgeschlagen).'
        $verifyText = & $Python -B $recovery --verify
        if ($LASTEXITCODE -ne 0) {
            throw 'HaloGen: Terminale Neustartpruefung fehlgeschlagen. Bitte Details oben pruefen und Model erneut starten; Schutzsperre unveraendert.'
        }
        $verified = ($verifyText -join [Environment]::NewLine) | ConvertFrom-Json
        if ($verified.run -ne 'a596d8b7119f4875b07ea1fedbc9768b' -or
            $verified.archived -ne $false -or $verified.requested_restart_gate_passed -ne $true -or $verified.historical_recovery -ne $false -or
            $verified.model_started -ne $false -or $verified.wsl_modified -ne $false -or
            [IO.Path]::GetDirectoryName([IO.Path]::GetFullPath([string]$verified.receipt)) -ne $Runtime -or
            [IO.Path]::GetFileName([string]$verified.receipt) -notmatch '^reconciliation-a596d8b7119f4875b07ea1fedbc9768b-verify-[0-9]{8}T[0-9]{6}Z-[0-9a-f]{8}\.json$') {
            throw 'HaloGen: Recovery-Nachweis unerwartet; Schutzsperre unveraendert.'
        }
        # The helper repeats identity/cleanup/lease checks and the requested restart gate; historical failure remains intact.
        $archiveText = & $Python -B $recovery --archive --verified-receipt ([string]$verified.receipt)
        if ($LASTEXITCODE -ne 0) { throw 'HaloGen: Frische 36-GiB-Neustartpruefung fehlgeschlagen; kein Modellstart.' }
        $archived = ($archiveText -join [Environment]::NewLine) | ConvertFrom-Json
        if ($archived.run -ne 'a596d8b7119f4875b07ea1fedbc9768b' -or $archived.archived -ne $true -or
            (Test-Path -LiteralPath $RunnerLock)) { throw 'HaloGen: Lock-Archivierung nicht bestaetigt; kein Modellstart.' }
        $state = Read-ControllerState
        $processes = @(Get-ModelProcesses)
        $listeners = @(Get-ListenerSnapshot)
        if ($null -eq $state -or $state.phase -ne 'failed' -or
            $state.run_id -ne 'ac678e51cef84d819a8fd276dcb93271' -or
            $processes.Count -or $listeners.Count) { throw 'HaloGen: Zustand nach Recovery veraendert; kein Modellstart.' }
        $phase = [string]$state.phase
        Write-Host 'HaloGen: angeforderte Neustartgrenze bestanden; historische Schutzsperre dokumentiert archiviert.'
    }
    if ($phase -notin @('absent', 'stopped', 'failed')) { throw 'HaloGen: Nicht abgeschlossener Controller-Zustand; keine automatische Reparatur.' }

    New-Item -ItemType Directory -Path $Runtime -Force | Out-Null
    $stamp = [datetime]::UtcNow.ToString('yyyyMMddTHHmmssfffZ')
    $stdout = Join-Path $Runtime "model-$stamp.stdout.log"
    $stderr = Join-Path $Runtime "model-$stamp.stderr.log"
    # Every new desktop Model start checks the configured physical/commit admission directly.
    # Existing managed runtime reserve remains 18 GiB; no live model is stopped here.
    $admissionText = & $Python -B $AdmissionScript --check-start
    if ($LASTEXITCODE -ne 0) { throw 'HaloGen: Start benoetigt 36 GiB freien physischen RAM und 131 GiB Commit-Reserve; kein Start.' }
    $admission = ($admissionText -join [Environment]::NewLine) | ConvertFrom-Json
    if ($admission.passed -ne $true -or $admission.gate -ne 'model_start') { throw 'HaloGen: Startgrenze nicht bestaetigt; kein Start.' }
    $arguments = @('-u', '-B', $Controller, 'run', '--config', $Profile, '--port', '8840')
    $started = Start-Process -FilePath $Python -ArgumentList $arguments -WorkingDirectory "$Clean\server" -WindowStyle Hidden -RedirectStandardOutput $stdout -RedirectStandardError $stderr -PassThru
    $receipt = [ordered]@{action='start_requested';utc=[datetime]::UtcNow.ToString('o');launcher_pid=$started.Id;
        launcher_start_ticks=$started.StartTime.ToUniversalTime().Ticks.ToString();python=$Python;controller=$Controller;
        profile=$Profile;profile_sha256=$ProfileHash;stdout=$stdout;stderr=$stderr;cache='Exact';context=262144;slots=1;minimum_reserve_gib=18;
        start_policy=$StartPolicy;start_policy_sha256=$StartPolicyHash;admission=$admission}
    $receipt | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $Runtime "model-launch-$stamp.json") -Encoding UTF8
    $receipt | ConvertTo-Json
    # The managed controller enforces admission, its independent guard and its
    # own controller lease. The coordinator waits for readiness; no retry here.
    exit 0
}
catch {
    Write-Error $_.Exception.Message
    exit 1
}
finally {
    if ($acquired -and $null -ne $mutex) { $mutex.ReleaseMutex() }
    if ($null -ne $mutex) { $mutex.Dispose() }
}
