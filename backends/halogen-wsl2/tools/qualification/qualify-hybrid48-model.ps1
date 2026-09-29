# Portable bounded controller derived from the frozen, qualified 32k research snapshot.
param([ValidateSet('PreflightTrace32k','PreflightPinned32k','PreflightPinned256k','PreflightSessions32k','PreflightServe32k')][string]$Mode = 'PreflightPinned32k', [ValidateRange(30,300)][int]$ServeSeconds=300)
$ErrorActionPreference = 'Stop'
$root = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
$results = Join-Path $root '.local/runs'
$python = (Get-Command python -ErrorAction Stop).Source
$pwsh = (Get-Command pwsh -ErrorAction Stop).Source
$image = 'ghcr.io/peonist-ai/halogen-flash-server@sha256:6e626c979d536ab1edb07898e278be6686afd353758ea268817457f801d687dd'
$wslArgs = @()
. (Join-Path $PSScriptRoot 'wait-lookup-runtime-guard.ps1')
. (Join-Path $PSScriptRoot 'portable-host.ps1')

function Stop-HelperChecked($Process, [switch]$Tree) {
    $Process.Refresh()
    if (-not $Process.HasExited) {
        $Process.Kill($true)
        if (-not $Process.WaitForExit(10000)) { throw 'Killed helper did not terminate within 10 seconds' }
        $Process.Refresh()
        if (-not $Process.HasExited) { throw 'Killed helper did not terminate within 10 seconds' }
    }
}

function Stop-QualificationProcess($Process, $Probe, [string]$Mode) {
    if ($Mode -ceq 'PreflightSessions32k' -and [object]::ReferenceEquals($Process,$Probe)) {
        Stop-HelperChecked $Process -Tree
    } else {
        Stop-HelperChecked $Process
    }
}

function Get-WindowsAvailableBytes {
    if (-not ('Hybrid48MemoryStatus' -as [type])) {
        Add-Type -TypeDefinition @'
using System;
using System.ComponentModel;
using System.Runtime.InteropServices;
public static class Hybrid48MemoryStatus {
    [StructLayout(LayoutKind.Sequential)]
    private struct Data {
        public uint Length, Load;
        public ulong TotalPhys, AvailPhys, TotalPageFile, AvailPageFile;
        public ulong TotalVirtual, AvailVirtual, AvailExtendedVirtual;
    }
    [DllImport("kernel32.dll", SetLastError = true)]
    private static extern bool GlobalMemoryStatusEx(ref Data data);
    public static long Available() {
        var data = new Data();
        data.Length = (uint)Marshal.SizeOf<Data>();
        if (!GlobalMemoryStatusEx(ref data)) throw new Win32Exception(Marshal.GetLastWin32Error());
        return checked((long)data.AvailPhys);
    }
}
'@
    }
    return [Hybrid48MemoryStatus]::Available()
}

function Invoke-WslBounded {
    param([string[]]$Arguments, [int]$Seconds = 30, [string]$CleanupSamples,
          [switch]$IncludeStderr)
    New-Item -ItemType Directory -Path $results -Force -ErrorAction Stop | Out-Null
    $stem = Join-Path $results ('helper-' + [guid]::NewGuid().ToString('N'))
    $out = "$stem.out"; $err = "$stem.err"
    $p = $null
    $observationErrors = @()
    $operationError = $null
    $cleanupErrors = @()
    $value = ''
    try {
        $p = Start-PortableProcess -FilePath 'wsl.exe' -WindowStyle Hidden -PassThru -ArgumentList ($wslArgs + $Arguments) -RedirectStandardOutput $out -RedirectStandardError $err
        if ($CleanupSamples) {
            try {
                $bytes = Get-WindowsAvailableBytes
                @{utc=[DateTime]::UtcNow.ToString('o'); availableBytes=$bytes} |
                    ConvertTo-Json -Compress | Add-Content -LiteralPath $CleanupSamples -Encoding utf8
            } catch { $observationErrors += [string]$_ }
        }
        $clock = [Diagnostics.Stopwatch]::StartNew()
        while (-not $p.WaitForExit(1000)) {
            if ($CleanupSamples) {
                try {
                    $bytes = Get-WindowsAvailableBytes
                    @{utc=[DateTime]::UtcNow.ToString('o'); availableBytes=$bytes} |
                        ConvertTo-Json -Compress | Add-Content -LiteralPath $CleanupSamples -Encoding utf8
                } catch { $observationErrors += [string]$_ }
            }
            if ($clock.Elapsed.TotalSeconds -ge $Seconds) {
                Stop-HelperChecked $p
                throw "Timed out WSL helper: $($Arguments[0])"
            }
        }
        if ($clock.Elapsed.TotalSeconds -gt $Seconds) {
            Stop-HelperChecked $p
            throw "Timed out WSL helper: $($Arguments[0])"
        }
        $value = if (Test-Path -LiteralPath $out) { [string](Get-Content -LiteralPath $out -Raw) } else { '' }
        $errorText = if (Test-Path -LiteralPath $err) { Get-Content -LiteralPath $err -Raw } else { '' }
        if ($p.ExitCode -ne 0) { throw "WSL helper failed ($($p.ExitCode)): $errorText" }
        if ($IncludeStderr -and $errorText) { $value += "`n" + $errorText }
        if ($CleanupSamples) {
            try {
                $bytes = Get-WindowsAvailableBytes
                @{utc=[DateTime]::UtcNow.ToString('o'); availableBytes=$bytes} |
                    ConvertTo-Json -Compress | Add-Content -LiteralPath $CleanupSamples -Encoding utf8
            } catch { $observationErrors += [string]$_ }
        }
        if ($observationErrors.Count) { throw "Cleanup memory observation failed: $($observationErrors -join '; ')" }
    } catch { $operationError = [string]$_ }
    finally {
        if ($p) {
            try { Stop-HelperChecked $p } catch { $cleanupErrors += "WSL helper cleanup: $_" }
            try { $p.Dispose() } catch { $cleanupErrors += "WSL helper dispose: $_" }
        }
        foreach ($path in @($out,$err)) {
            try { if (Test-Path -LiteralPath $path) { Remove-Item -LiteralPath $path -Force } }
            catch { $cleanupErrors += "WSL helper temporary file: $_" }
        }
    }
    if ($operationError -or $cleanupErrors.Count) { throw (@($operationError) + $cleanupErrors | Where-Object { $_ }) -join '; ' }
    return ([string]$value).Trim()
}

function Assert-Hash([string]$Path, [string]$Expected) {
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) { throw "Missing required file: $Path" }
    $actual = (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($actual -cne $Expected) { throw "Hash mismatch: $Path" }
    return $actual
}

function Assert-PreflightBuild {
    $manifestPath = Join-Path $root 'profiles/build.json'
    Assert-Hash $manifestPath '4ba62f3db0359b6bf4a3f3a0727ab4bb3992cd64f7326469b0794b0a213d9edd' | Out-Null
    $build = Get-Content -LiteralPath $manifestPath -Raw | ConvertFrom-Json -ErrorAction Stop
    if ($build.schema -cne 'halogen-preflight-build-v1' -or
        $build.profile -cne 'flash0138-copy48-v1' -or
        $build.hybridProfile -cne 'vgm64-copy48-v1' -or
        $build.engineSha256 -cne '39382df17e7bd922a302d7dbfaaaa80d5dbb4a813e50268265a74c70c8679625' -or
        [int64]$build.copyCapBytes -ne 51539607552 -or [int64]$build.hostCapBytes -ne 25769803776 -or
        @($build.sources).Count -ne 4 -or @($build.adapters).Count -ne 2) {
        throw 'Sealed preflight build identity changed'
    }
    $sourcePaths = @('patches/hip-register-hybrid.c','patches/hip-preflight-plan.h',
                     'patches/halogen-preflight-bridge.c','patches/halogen-preflight-trampoline.S')
    $sourceHashes = @('6580422cd5f50e6e99f9a716b0c073922333e64dc484e48854c9764c03825dc0',
                      'bbf72a9dd29efd4a3c70caa9dc67b1393203ff412c140184eaee90c4bc25397b',
                      '3a365e6a36e12b70980b69ed07d42b933a9a639177d6a70955035c227f294e93',
                      '77f30756961d2e1680af8e162c2634e57b1e638ac2cf963796ad1f5fc409aa99')
    for ($i=0; $i -lt 4; $i++) {
        if ($build.sources[$i].path -cne $sourcePaths[$i] -or $build.sources[$i].sha256 -cne $sourceHashes[$i]) {
            throw 'Sealed preflight source identity changed'
        }
        Assert-Hash (Join-Path $root $sourcePaths[$i]) $sourceHashes[$i] | Out-Null
    }
    $binaryPaths = @('bin/halogen-preflight-adadd8dd5cebcdf559fcc9df767a2bcb36e6946c1a123b90c670320bf7a873f5.so',
                     'bin/hip-register-private-rw-vgm64copy48-0546a8817fdec642ae3e9b597a9912b547ccd743d6da7eda923d647d0d421c9c.so')
    $binaryHashes = @('adadd8dd5cebcdf559fcc9df767a2bcb36e6946c1a123b90c670320bf7a873f5',
                      'f567e21d5c7293ce75f62d36e57bf65915640c11fb2c753b39757d17b3ed034d')
    for ($i=0; $i -lt 2; $i++) {
        $role = if ($i -eq 0) { 'preflight-hybrid' } else { 'private' }
        if ($build.adapters[$i].role -cne $role -or $build.adapters[$i].binary -cne $binaryPaths[$i] -or
            $build.adapters[$i].binarySha256 -cne $binaryHashes[$i]) {
            throw 'Sealed preflight preload identity or order changed'
        }
        Assert-Hash (Join-Path $root $binaryPaths[$i]) $binaryHashes[$i] | Out-Null
    }
    if ($build.adapters[1].source -cne 'patches/hip-register-private-rw.c' -or
        $build.adapters[1].sourceSha256 -cne '0546a8817fdec642ae3e9b597a9912b547ccd743d6da7eda923d647d0d421c9c') {
        throw 'Sealed private adapter identity changed'
    }
    Assert-Hash (Join-Path $root $build.adapters[1].source) $build.adapters[1].sourceSha256 | Out-Null
    return $build
}

function Get-WindowsLaunchReserve {
    $available = [int64](Get-CimInstance Win32_PerfFormattedData_PerfOS_Memory -ErrorAction Stop).AvailableBytes
    if ($available -lt 52613349376) { throw 'Require at least 49 GiB Windows available' }
    return $available
}

function Assert-Admission {
    param([string]$Mode)
    return Assert-PublicAdmission
}

function New-RunArguments($reference, $admission, [string]$name,
                          [ValidateSet('PreflightTrace32k','PreflightPinned32k','PreflightPinned256k','PreflightSessions32k','PreflightServe32k')][string]$Mode = 'PreflightPinned32k') {
    $expectedBinds = @(Get-PublicBinds)
    if ($reference.Config.Image -cne $image -or
        (@($reference.HostConfig.Binds) -join '|') -cne ($expectedBinds -join '|')) {
        throw 'Reference image or read-only binds changed'
    }
    $envMap = @{}
    foreach ($entry in $reference.Config.Env) {
        $pair = $entry -split '=',2
        if ($envMap.ContainsKey($pair[0])) { throw 'Duplicate reference environment key' }
        $envMap[$pair[0]] = $pair[1]
    }
    $frozen = @{
      'HALOGEN_CTX'='32768'; 'HALOGEN_KV_POOL_POSITIONS'='32768'; 'HALOGEN_KV_SLOTS'='1';
      'HALOGEN_PREFILL_CHUNK'='2048'; 'HALOGEN_MAX_TOK'='2048'; 'HALOGEN_PROMPT_CACHE'='0';
      'HALOGEN_HYBRID_RECLAIM_COPY'='1'; 'HALOGEN_FLASH_ROUTE_GEMM'='0';
      'HALOGEN_FLASH_PIN_TRUNK'='1'; 'HSA_ENABLE_SDMA'='1'; 'HALOGEN_HOST_RESERVE_GIB'='12';
      'HALOGEN_CHECKPOINT'='/models/qwen38-flash-next-w4b.hgn'; 'HALOGEN_API_PORT'='8731'
    }
    foreach ($key in $frozen.Keys) {
        if ($envMap[$key] -cne $frozen[$key]) { throw "Frozen reference parameter changed: $key" }
    }
    if ($envMap.ContainsKey('HALOGEN_LOOKUP_RANDOM')) { throw 'Lookup-random configuration prohibited' }
    $argsRun = @('create','--name',$name,'--label','halogen.performance=hybrid',
        '--label','strix-alloy.owner=strix-alloy-wsl2','--label',("strix-alloy.run=" + $name),
        '--device','/dev/dxg','--cap-add','SYS_PTRACE','--security-opt','seccomp=unconfined',
        '--security-opt','label=disable','--ipc','host','--shm-size','8g','--ulimit','memlock=-1:-1',
        '--memory','47244640256','--memory-swap','47244640256','-p','127.0.0.1:8731:8731')
    foreach ($bind in $expectedBinds) { $argsRun += @('-v',$bind) }
    $overrides = @{
        'HALOGEN_HYBRID_COPY_BYTES'='51539607552';
        'HALOGEN_HYBRID_PROFILE'='vgm64-copy48-v1'
    }
    if ($Mode -ceq 'PreflightPinned256k') {
        $overrides['HALOGEN_CTX'] = '262144'
        $overrides['HALOGEN_KV_POOL_POSITIONS'] = '262144'
    }
    if ($Mode -ceq 'PreflightSessions32k') { $overrides['HALOGEN_KV_SLOTS'] = '3' }
    if ($Mode -like 'Preflight*') {
        if (@($admission.adapters).Count -ne 2 -or
            $admission.adapters[0].binary -cne 'bin/halogen-preflight-adadd8dd5cebcdf559fcc9df767a2bcb36e6946c1a123b90c670320bf7a873f5.so' -or
            $admission.adapters[1].binary -cne 'bin/hip-register-private-rw-vgm64copy48-0546a8817fdec642ae3e9b597a9912b547ccd743d6da7eda923d647d0d421c9c.so') {
            throw 'Preflight preload order changed'
        }
        $overrides['HALOGEN_PREFLIGHT_PROFILE'] = 'flash0138-copy48-v1'
        $overrides['HALOGEN_PREFLIGHT_TRACE_ONLY'] = if ($Mode -ceq 'PreflightTrace32k') { '1' } else { '0' }
    }
    $preloads = @($admission.adapters | ForEach-Object { '/workspace/' + $_.binary }) -join ':'
    $seen = @{}
    foreach ($entry in $reference.Config.Env) {
        $key = ($entry -split '=',2)[0]
        if ($key -eq 'LD_PRELOAD') { $entry = "LD_PRELOAD=$preloads" }
        elseif ($overrides.ContainsKey($key)) { $entry = "$key=$($overrides[$key])" }
        $seen[$key] = $true
        $argsRun += @('--env',$entry)
    }
    $requiredOverrides = @('HALOGEN_HYBRID_COPY_BYTES','HALOGEN_HYBRID_PROFILE')
    if ($Mode -like 'Preflight*') { $requiredOverrides += @('HALOGEN_PREFLIGHT_PROFILE','HALOGEN_PREFLIGHT_TRACE_ONLY') }
    foreach ($key in $requiredOverrides) {
        if (-not $seen.ContainsKey($key)) { $argsRun += @('--env',"$key=$($overrides[$key])") }
    }
    if (-not $seen.ContainsKey('LD_PRELOAD')) { throw 'Reference preload missing' }
    $argsRun += @('--entrypoint','/usr/bin/timeout',$image,
                  '--signal=TERM','--kill-after=10s','900s','/usr/local/bin/entrypoint.sh','all')
    return ,$argsRun
}

function Write-RunJson([string]$Path, $Value) {
    $json = $Value | ConvertTo-Json -Depth 12
    $file = [IO.File]::Open($Path, [IO.FileMode]::CreateNew, [IO.FileAccess]::Write)
    try { $bytes = [Text.Encoding]::UTF8.GetBytes($json + "`n"); $file.Write($bytes,0,$bytes.Length) }
    finally { $file.Dispose() }
}

function Write-MemoryObservation {
    param([string]$ContainerId, [string]$Path, [string]$Phase)
    $began = [DateTime]::UtcNow
    $memory = Get-CimInstance Win32_PerfFormattedData_PerfOS_Memory -ErrorAction Stop
    $instances = @(Get-CimInstance Win32_PerfFormattedData_GPUPerformanceCounters_GPUAdapterMemory -ErrorAction Stop)
    if ($null -eq $memory.AvailableBytes -or $null -eq $memory.CommittedBytes -or $null -eq $memory.CommitLimit -or
        $instances.Count -eq 0) { throw 'Incomplete Windows memory telemetry' }
    $gpu = @()
    foreach ($instance in $instances) {
        if (-not $instance.Name -or $null -eq $instance.DedicatedUsage -or $null -eq $instance.SharedUsage -or
            $null -eq $instance.TotalCommitted) { throw 'Incomplete per-instance GPU telemetry' }
        $gpu += @{name=[string]$instance.Name; dedicatedBytes=[int64]$instance.DedicatedUsage;
                  sharedBytes=[int64]$instance.SharedUsage; totalCommittedBytes=[int64]$instance.TotalCommitted}
    }
    $guest = [ordered]@{}
    foreach ($metric in @('memory.current','memory.peak','memory.swap.current')) {
        $value = Invoke-WslBounded -Arguments @('docker','exec',$ContainerId,'cat',"/sys/fs/cgroup/$metric") -Seconds 5
        if ($value -notmatch '^\d+$') { throw "Invalid cgroup $metric telemetry" }
        $guest[$metric] = [int64]$value
    }
    $rss = Invoke-WslBounded -Arguments @('docker','top',$ContainerId,'-eo','pid,rss,comm') -Seconds 5
    if (-not $rss -or $rss -notmatch '(?i)rss') { throw 'Missing process RSS telemetry' }
    $ended = [DateTime]::UtcNow
    if (($ended - $began).TotalSeconds -gt 30) { throw 'Memory observation exceeded 30-second limit' }
    $record = @{schema='hybrid48-memory-v1'; phase=$Phase; containerId=$ContainerId;
        beganUtc=$began.ToString('o'); endedUtc=$ended.ToString('o');
        targetIntervalSeconds=10; maxObservationSeconds=30;
        windows=@{availableBytes=[int64]$memory.AvailableBytes; committedBytes=[int64]$memory.CommittedBytes;
                  commitLimitBytes=[int64]$memory.CommitLimit}; gpuInstances=$gpu; guest=$guest; processRssRaw=$rss;
        note='Raw per-instance counters; not exact total model residency'}
    Write-RunJson $Path $record
    $saved = Get-Content -LiteralPath $Path -Raw | ConvertFrom-Json -ErrorAction Stop
    $savedEndUtc = if ($saved.endedUtc -is [DateTime]) { $saved.endedUtc.ToUniversalTime() }
        else { [DateTimeOffset]::Parse([string]$saved.endedUtc,[Globalization.CultureInfo]::InvariantCulture).UtcDateTime }
    if ($saved.containerId -cne $ContainerId -or $saved.phase -cne $Phase -or
        @($saved.gpuInstances).Count -ne $instances.Count -or $null -eq $saved.guest.'memory.peak' -or
        [DateTime]::UtcNow.Subtract($savedEndUtc).TotalSeconds -gt 30) {
        throw 'Memory telemetry artifact failed validation'
    }
    return $record
}

function Assert-MemoryArtifact([string]$ContainerId, [string]$Path, [string]$Phase) {
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) { throw 'Memory telemetry artifact missing' }
    $saved = Get-Content -LiteralPath $Path -Raw | ConvertFrom-Json -ErrorAction Stop
    $savedEndUtc = if ($saved.endedUtc -is [DateTime]) { $saved.endedUtc.ToUniversalTime() }
        else { [DateTimeOffset]::Parse([string]$saved.endedUtc,[Globalization.CultureInfo]::InvariantCulture).UtcDateTime }
    $savedBeginUtc = if ($saved.beganUtc -is [DateTime]) { $saved.beganUtc.ToUniversalTime() }
        else { [DateTimeOffset]::Parse([string]$saved.beganUtc,[Globalization.CultureInfo]::InvariantCulture).UtcDateTime }
    $age = [DateTime]::UtcNow.Subtract($savedEndUtc).TotalSeconds
    if ($saved.schema -cne 'hybrid48-memory-v1' -or $saved.containerId -cne $ContainerId -or
        $saved.phase -cne $Phase -or $age -lt -5 -or $age -gt 30 -or
        ($savedEndUtc - $savedBeginUtc).TotalSeconds -lt 0 -or
        ($savedEndUtc - $savedBeginUtc).TotalSeconds -gt 30 -or
        @($saved.gpuInstances).Count -eq 0 -or $null -eq $saved.windows.availableBytes -or
        $null -eq $saved.windows.committedBytes -or $null -eq $saved.windows.commitLimitBytes -or
        $null -eq $saved.guest.'memory.current' -or $null -eq $saved.guest.'memory.peak' -or
        $null -eq $saved.guest.'memory.swap.current' -or -not $saved.processRssRaw) {
        throw 'Memory telemetry artifact failed validation'
    }
    foreach ($instance in @($saved.gpuInstances)) {
        if (-not $instance.name -or $null -eq $instance.dedicatedBytes -or
            $null -eq $instance.sharedBytes -or $null -eq $instance.totalCommittedBytes) {
            throw 'Memory telemetry lacks raw per-instance counters'
        }
    }
    return $saved
}

function Get-RemainingInferenceSeconds {
    param([double]$InferenceElapsed, [double]$OverallElapsed,
          [ValidateSet('PreflightTrace32k','PreflightPinned32k','PreflightPinned256k','PreflightSessions32k','PreflightServe32k')][string]$Mode = 'PreflightPinned32k')
    $phaseSeconds = if ($Mode -ceq 'PreflightPinned256k') { 600 } else { 400 }
    $remaining = [int][Math]::Floor([Math]::Min($phaseSeconds - $InferenceElapsed, 820 - $OverallElapsed))
    if ($remaining -lt 1) { throw 'Inference window exhausted before telemetry' }
    return $remaining
}

function Get-QualificationProbeSpec([ValidateSet('PreflightTrace32k','PreflightPinned32k','PreflightPinned256k','PreflightSessions32k','PreflightServe32k')][string]$Mode = 'PreflightPinned32k') {
    if ($Mode -ceq 'PreflightServe32k') { return @{Script='serve32k.py';Output='serve.json';LogStem='serve';DeadlineSeconds=($ServeSeconds + 10)} }
    if ($Mode -ceq 'PreflightTrace32k') { return @{Script=$null; Output=$null; LogStem=$null; DeadlineSeconds=0} }
    if ($Mode -ceq 'PreflightSessions32k') {
        return @{Script='hybrid48-sessions-check.py'; Output='sessions-check.json';
                 LogStem='sessions-check'; DeadlineSeconds=300}
    }
    if ($Mode -ceq 'PreflightPinned256k') {
        return @{Script='hybrid48-context-check.py'; Output='context-check.json';
                 LogStem='context-check'; DeadlineSeconds=570; LargeRequestSeconds=500}
    }
    return @{Script='hybrid48-prose-check.py'; Output='prose128.json';
             LogStem='prose'; DeadlineSeconds=400}
}

function Get-QualificationProbeArguments {
    param($Spec, [string]$Mode, [int]$Window, [string]$RunDir)
    $probeArgs = @((Join-Path $PSScriptRoot $Spec.Script),'--output',(Join-Path $RunDir $Spec.Output))
    if ($Mode -ceq 'PreflightPinned256k') { $probeArgs += @('--mode',$Mode,'--deadline-seconds',([string]$Window)) }
    if ($Mode -ceq 'PreflightSessions32k') { $probeArgs += @('--deadline-seconds',([string]$Window)) }
    if ($Mode -ceq 'PreflightServe32k') { $probeArgs += @('--seconds',[string]$ServeSeconds) }
    return ,$probeArgs
}

function Assert-PreflightBridgeIdentity([string[]]$Lines, [int]$Trace) {
    $active = @($Lines | Where-Object {
        $_ -cmatch '^\[preflight-bridge\] active sha256=39382df17e7bd922a302d7dbfaaaa80d5dbb4a813e50268265a74c70c8679625 rva=0xc8f020 trace=([01])$' -and
        [int]$Matches[1] -eq $Trace
    })
    if ($active.Count -ne 1) { throw 'Preflight bridge actual engine identity or trace mode missing' }
}

function Assert-PreflightSafetyLog([string[]]$Lines) {
    if (@($Lines | Where-Object {
        $_ -match '(?i)^\[preflight\] reject\b|^\[preflight-bridge\] fatal\b|^\[preflight\] poison\b|^\[hybrid\] failed-copy cleanup HIP error=[1-9]|^\[hybrid\] device-copy bytes=\d+ result=[1-9]|^(?:hip|flash_serve|checkpoint):.*(?:out of memory|\boom\b)|^HIP error at .+:\d+: .+|^hipBLASLt error at .+:\d+: status \d+'
    }).Count) { throw 'Preflight rejection, poison, or memory error in workload log' }
}

function Assert-PreflightCompletionEvidence([string]$LogPath) {
    if (-not (Test-Path -LiteralPath $LogPath -PathType Leaf)) { throw 'Preflight workload log missing' }
    $lines = @(Get-Content -LiteralPath $LogPath)
    Assert-PreflightBridgeIdentity -Lines $lines -Trace 0
    Assert-PreflightSafetyLog -Lines $lines
    $first = @($lines | Where-Object { $_ -ceq '[preflight] complete phase=1 copied=50433337536 host=20001656832' })
    $second = @($lines | Where-Object { $_ -ceq '[preflight] complete phase=2 copied=50433337536 host=22574008704' })
    if ($first.Count -ne 1 -or $second.Count -ne 1 -or
        @($lines | Where-Object { $_ -cmatch '^\[preflight\] complete\b' }).Count -ne 2 -or
        [array]::IndexOf($lines,$first[0]) -ge [array]::IndexOf($lines,$second[0])) {
        throw 'Preflight allocation completion missing or disagrees with expected cumulative bytes'
    }
}

function Assert-PreflightTraceEvidence([string]$LogPath, $PreStop, $Terminal, $AttachedClient) {
    if (-not (Test-Path -LiteralPath $LogPath -PathType Leaf)) { throw 'Preflight trace log missing' }
    $lines = @(Get-Content -LiteralPath $LogPath)
    Assert-PreflightBridgeIdentity -Lines $lines -Trace 1
    Assert-PreflightSafetyLog -Lines $lines
    if (@($lines | Where-Object { $_ -match '^\[preflight\] complete\b|^\[hybrid\] device-copy bytes=|^\[private-rw\] (?:register|refuse)\b|^\[preflight\] reject\b' }).Count) {
        throw 'Trace continued into registration or copy'
    }
    if (@($lines | Where-Object { $_ -ceq '[preflight] plan phase=1 ranges=252 aggregate=70434994368 copy=50433337536 host=20001656832' }).Count -ne 1 -or
        @($lines | Where-Object { $_ -ceq '[preflight-bridge] demand aggregate=70434994368 host=20001656832 mapping=124068083904 count=252 floor=17179869184' }).Count -ne 1) {
        throw 'Trace vector plan or demand bytes differ from reviewed preflight'
    }
    $ranges = @($lines | Where-Object { $_ -cmatch '^\[preflight-bridge\] range\[' })
    if ($ranges.Count -ne 252) { throw 'Trace range count differs from reviewed vector' }
    for ($i=0; $i -lt 252; $i++) {
        if ($ranges[$i] -cnotmatch '^\[preflight-bridge\] range\[(\d+)\]=(\d+):(\d+)$' -or
            [int]$Matches[1] -ne $i -or [uint64]$Matches[3] -le [uint64]$Matches[2]) {
            throw 'Trace range index or bounds invalid'
        }
    }
    if ($null -eq $PreStop -or $null -eq $Terminal -or $null -eq $AttachedClient -or
        -not $AttachedClient.HasExited -or $null -eq $AttachedClient.ExitCode -or
        [int]$AttachedClient.ExitCode -ne 1) {
        throw 'Trace attached client did not exit naturally with wrapper code 1'
    }
    foreach ($state in @($PreStop.State,$Terminal.State)) {
        if ($null -eq $state -or $null -eq $state.Running -or $state.Running -or
            $null -eq $state.Pid -or [int]$state.Pid -ne 0 -or
            $null -eq $state.OOMKilled -or $state.OOMKilled -or
            $null -eq $state.Error -or $state.Error -or
            $null -eq $state.ExitCode -or [int]$state.ExitCode -ne 1) {
            throw 'Trace container did not exit naturally with wrapper code 1'
        }
    }
    return @{classification='diagnostic'; expectedEngineExitCode=77;
             engineExitObserved=$false; preStopExitCode=[int]$PreStop.State.ExitCode;
             containerExitCode=[int]$Terminal.State.ExitCode;
             attachedExitCode=[int]$AttachedClient.ExitCode; traceRanges=$ranges.Count}
}

function Invoke-MemoryObservationBounded {
    param([string]$ContainerId, [string]$Path, [string]$Phase, [int]$Seconds)
    if ($Seconds -lt 1 -or $Seconds -gt 30) { throw 'Invalid bounded telemetry allowance' }
    $worker = $null; $primaryError = $null; $cleanupErrors = @(); $record = $null
    $clock = [Diagnostics.Stopwatch]::StartNew()
    try {
        $worker = Start-PortableProcess -FilePath $pwsh -WindowStyle Hidden -PassThru -ArgumentList @(
            '-NoProfile','-File',(Join-Path $PSScriptRoot 'sample-hybrid48-memory.ps1'),
            '-ContainerId',$ContainerId,'-Output',$Path,'-Phase',$Phase) `
            -RedirectStandardOutput "$Path.stdout.log" -RedirectStandardError "$Path.stderr.log"
        $waitMilliseconds = [int][Math]::Floor($Seconds * 1000 - $clock.Elapsed.TotalMilliseconds)
        if ($waitMilliseconds -lt 1 -or -not $worker.WaitForExit($waitMilliseconds)) {
            throw "Memory observation exceeded ${Seconds}-second phase allowance"
        }
        $worker.Refresh()
        if (-not $worker.HasExited) { throw 'Memory observation worker did not exit after wait' }
        if ($worker.ExitCode -ne 0) { throw "Memory observation worker failed (code $($worker.ExitCode))" }
        $record = Assert-MemoryArtifact -ContainerId $ContainerId -Path $Path -Phase $Phase
        if ($clock.Elapsed.TotalSeconds -gt $Seconds) { throw "Memory observation exceeded ${Seconds}-second phase allowance" }
    } catch { $primaryError = [string]$_ }
    finally {
        if ($worker) {
            try { Stop-HelperChecked $worker -Tree } catch { $cleanupErrors += "memory worker cancellation: $_" }
            try { $worker.Dispose() } catch { $cleanupErrors += "memory worker dispose: $_" }
        }
    }
    if ($primaryError -or $cleanupErrors.Count) {
        throw (@($primaryError) + $cleanupErrors | Where-Object { $_ }) -join '; '
    }
    return $record
}

function Get-RemainingStartupSeconds([double]$ElapsedSeconds) {
    $remaining = [int][Math]::Floor(420 - $ElapsedSeconds)
    if ($remaining -lt 1) { throw 'Startup including handoff exceeded 420 seconds' }
    return $remaining
}

function Wait-ContainerRunning {
    param([string]$ContainerId, $AttachedClient, [Diagnostics.Stopwatch]$Clock,
          [int]$TimeoutSeconds = 420)
    if ($ContainerId -notmatch '^[0-9a-f]{64}$') { throw 'Invalid start acknowledgement target' }
    while ($Clock.Elapsed.TotalSeconds -lt $TimeoutSeconds) {
        $AttachedClient.Refresh()
        if ($AttachedClient.HasExited) { throw "Attached start client exited before running acknowledgement (code $($AttachedClient.ExitCode))" }
        $available = Get-WindowsAvailableBytes
        if ($available -lt 20GB) { throw 'Windows RAM below startup abort floor during start acknowledgement' }
        $left = Get-RemainingStartupSeconds -ElapsedSeconds $Clock.Elapsed.TotalSeconds
        $state = Invoke-WslBounded -Arguments @('docker','inspect','--format','{{.Id}}|{{.State.Running}}',$ContainerId) -Seconds ([Math]::Min(5,$left))
        if ($state -ceq "$ContainerId|true") {
            $AttachedClient.Refresh()
            if ($AttachedClient.HasExited) { throw "Attached start client exited before running acknowledgement (code $($AttachedClient.ExitCode))" }
            return
        }
        if ($state -cne "$ContainerId|false") { throw "Invalid start acknowledgement state: $state" }
        Start-Sleep -Milliseconds 250
    }
    throw 'Container start acknowledgement exceeded startup allowance'
}

function Wait-PreflightTraceExit {
    param([string]$ContainerId, $AttachedClient, [Diagnostics.Stopwatch]$Clock)
    if ($ContainerId -notmatch '^[0-9a-f]{64}$') { throw 'Invalid trace container ID' }
    while ($Clock.Elapsed.TotalSeconds -lt 420) {
        $available = Get-WindowsAvailableBytes
        if ($available -lt 20GB) { throw 'Windows RAM below startup abort floor during trace' }
        $left = Get-RemainingStartupSeconds -ElapsedSeconds $Clock.Elapsed.TotalSeconds
        $raw = Invoke-WslBounded -Arguments @('docker','inspect',$ContainerId) -Seconds ([Math]::Min(5,$left))
        $state = @($raw | ConvertFrom-Json -ErrorAction Stop)[0]
        if ($state.Id -cne $ContainerId -or $null -eq $state.State.Running -or
            $null -eq $state.State.OOMKilled -or $null -eq $state.State.Error) {
            throw 'Invalid trace container state'
        }
        if ($state.State.OOMKilled -or $state.State.Error) { throw 'Trace container OOM or error' }
        if (-not $state.State.Running) {
            if (-not $state.State.StartedAt -or ([DateTime]$state.State.StartedAt).Year -le 1 -or
                -not $state.State.FinishedAt -or ([DateTime]$state.State.FinishedAt).Year -le 1) {
                $AttachedClient.Refresh()
                if ($AttachedClient.HasExited) { throw 'Attached trace client exited before container start' }
                Start-Sleep -Milliseconds 250
                continue
            }
            if ([int]$state.State.Pid -ne 0 -or $null -eq $state.State.ExitCode) {
                throw 'Trace container did not reach safe terminal state'
            }
            if ((Get-WindowsAvailableBytes) -lt 24GB) { throw 'Windows RAM below 24 GiB trace terminal floor' }
            $AttachedClient.Refresh()
            if (-not $AttachedClient.HasExited) {
                $left = Get-RemainingStartupSeconds -ElapsedSeconds $Clock.Elapsed.TotalSeconds
                if (-not $AttachedClient.WaitForExit([Math]::Min(10000,$left * 1000))) {
                    throw 'Attached trace client did not exit after container terminal state'
                }
                $AttachedClient.Refresh()
                if (-not $AttachedClient.HasExited) { throw 'Attached trace client did not exit after container terminal state' }
            }
            return $state
        }
        $AttachedClient.Refresh()
        if ($AttachedClient.HasExited) { throw "Attached trace client exited while container remained running (code $($AttachedClient.ExitCode))" }
        Start-Sleep -Milliseconds 250
    }
    throw 'Trace exceeded 420-second startup allowance'
}

function Invoke-Qualification {
    param([ValidateSet('PreflightTrace32k','PreflightPinned32k','PreflightPinned256k','PreflightSessions32k','PreflightServe32k')][string]$Mode = 'PreflightPinned32k')
    Initialize-PublicMachine
    $admission = Assert-Admission -Mode $Mode
    $reference = Get-PublicReference
    $stamp = [DateTime]::UtcNow.ToString('yyyyMMdd-HHmmss')
    $nonce = [guid]::NewGuid().ToString('N')
    $name = "halogen-flash-hybrid-model-$stamp-$nonce"
    $runDir = Join-Path $results ($stamp + '-' + $nonce)
    $argsRun = New-RunArguments $reference $admission $name -Mode $Mode
    $probeSpec = Get-QualificationProbeSpec -Mode $Mode
    New-Item -ItemType Directory -Path $results -Force -ErrorAction Stop | Out-Null
    New-Item -ItemType Directory -Path $runDir -ErrorAction Stop | Out-Null
    Write-RunJson (Join-Path $runDir 'admission.json') @{utc=[DateTime]::UtcNow.ToString('o'); mode=$Mode; admission=$admission; args=$argsRun}
    $container = $null; $waiter = $null; $runtime = $null; $guard = $null; $probe = $null
    $failure = $null; $cleanupErrors = @(); $start = [Diagnostics.Stopwatch]::StartNew()
    $observationCount = 0; $finalTelemetry = $false
    $traceEvidence = $null; $terminal = $null
    try {
        # docker create yields the exact ID before any long-running workload begins.
        $container = Invoke-WslBounded -Arguments (@('docker') + $argsRun) -Seconds 30
        if ($container -notmatch '^[0-9a-f]{64}$') { throw 'Invalid docker create ID' }
        Write-RunJson (Join-Path $runDir 'container-id.json') @{id=$container}
        $waiter = Start-PortableProcess -FilePath 'wsl.exe' -WindowStyle Hidden -PassThru -ArgumentList ($wslArgs + @('docker','start','-a',$container)) -RedirectStandardOutput (Join-Path $runDir 'attached-start.log') -RedirectStandardError (Join-Path $runDir 'attached-start-stderr.log')
        if ($Mode -ceq 'PreflightTrace32k') {
            $null = Wait-PreflightTraceExit -ContainerId $container -AttachedClient $waiter -Clock $start
        } else {
            Wait-ContainerRunning -ContainerId $container -AttachedClient $waiter -Clock $start
        }
        Write-RunJson (Join-Path $runDir 'processes.json') @{containerId=$container; attachedPid=$waiter.Id}
        if ($Mode -cne 'PreflightTrace32k') {
        $guard = Start-PortableProcess -FilePath $python -WindowStyle Hidden -PassThru -ArgumentList (@('-B',(Join-Path $root 'scripts\guard-halogen-startup.py'),'--container-id',$container,'--output',(Join-Path $runDir 'startup-guard.jsonl')) + $guardArgs) -RedirectStandardOutput (Join-Path $runDir 'startup-guard.log') -RedirectStandardError (Join-Path $runDir 'startup-guard-stderr.log')
        try {
            $left = Get-RemainingStartupSeconds -ElapsedSeconds $start.Elapsed.TotalSeconds
            if (-not $guard.WaitForExit($left * 1000)) { throw 'Startup including guard cleanup exceeded 420 seconds' }
            if ($guard.ExitCode -ne 0) { throw 'Startup guard rejected run; no inference allowed' }
        } finally { }
        if ($start.Elapsed.TotalSeconds -ge 420) { throw 'Startup exceeded 420 seconds' }
        $runtimeStarted = [DateTime]::UtcNow
        $runtimeLog = Join-Path $runDir 'runtime-guard.jsonl'
        $runtime = Start-PortableProcess -FilePath $python -WindowStyle Hidden -PassThru -ArgumentList (@('-B',(Join-Path $root 'scripts\guard-halogen-startup.py'),'--container-id',$container,'--output',$runtimeLog,'--runtime-seconds','900') + $guardArgs) -RedirectStandardOutput (Join-Path $runDir 'runtime-guard.log') -RedirectStandardError (Join-Path $runDir 'runtime-guard-stderr.log')
        $handoffSeconds = Get-RemainingStartupSeconds -ElapsedSeconds $start.Elapsed.TotalSeconds
        Wait-LookupRuntimeGuard -Process $runtime -LogPath $runtimeLog -ContainerId $container -NotBeforeUtc $runtimeStarted -TimeoutSeconds $handoffSeconds
        if ($start.Elapsed.TotalSeconds -ge 420) { throw 'Startup handoff exceeded 420 seconds' }
        if ($Mode -like 'Preflight*') {
            $preProbeLog = Join-Path $runDir 'pre-probe-container.log'
            $attachedError = Join-Path $runDir 'attached-start-stderr.log'
            if (-not (Test-Path -LiteralPath $attachedError -PathType Leaf)) { throw 'Attached native stderr missing' }
            Get-Content -LiteralPath $attachedError -Raw | Set-Content -LiteralPath $preProbeLog -Encoding utf8
            Assert-PreflightCompletionEvidence -LogPath $preProbeLog
        }
        $inference = [Diagnostics.Stopwatch]::StartNew()
        $inferenceLimit = if ($Mode -ceq 'PreflightPinned256k') { 600 } else { 400 }
        $observationIndex = 0
        $allowance = [Math]::Min(30,(Get-RemainingInferenceSeconds -InferenceElapsed $inference.Elapsed.TotalSeconds -OverallElapsed $start.Elapsed.TotalSeconds -Mode $Mode))
        $null = Invoke-MemoryObservationBounded -ContainerId $container -Path (Join-Path $runDir ('memory-{0:d3}.json' -f $observationIndex)) -Phase 'ready' -Seconds $allowance
        $observationCount++
        $lastObservation = [Diagnostics.Stopwatch]::StartNew()
        $null = Get-RemainingInferenceSeconds -InferenceElapsed $inference.Elapsed.TotalSeconds -OverallElapsed $start.Elapsed.TotalSeconds -Mode $Mode
        $probeClock = [Diagnostics.Stopwatch]::StartNew()
        $probeWindow = [Math]::Min($probeSpec.DeadlineSeconds,
            (Get-RemainingInferenceSeconds -InferenceElapsed $inference.Elapsed.TotalSeconds -OverallElapsed $start.Elapsed.TotalSeconds -Mode $Mode))
        $probeArgs = Get-QualificationProbeArguments -Spec $probeSpec -Mode $Mode -Window $probeWindow -RunDir $runDir
        $probe = Start-PortableProcess -FilePath $python -WindowStyle Hidden -PassThru -ArgumentList $probeArgs -RedirectStandardOutput (Join-Path $runDir ($probeSpec.LogStem + '.log')) -RedirectStandardError (Join-Path $runDir ($probeSpec.LogStem + '-stderr.log'))
        $serveAnnounced = $false
        while ($true) {
            $probe.Refresh()
            if ($probe.HasExited) { break }
            $runtime.Refresh()
            $waiter.Refresh()
            if ($runtime.HasExited -or $waiter.HasExited) { throw 'Owned guard or attached start client exited during request supervision' }
            if ($Mode -ceq 'PreflightServe32k' -and -not $serveAnnounced -and (Test-Path -LiteralPath (Join-Path $runDir 'serve.json'))) {
                Write-Host "API ready at http://127.0.0.1:8731 for a bounded $ServeSeconds-second window. Keep this foreground command running."
                $serveAnnounced = $true
            }
            if ($probeClock.Elapsed.TotalSeconds -ge $probeWindow -or
                $inference.Elapsed.TotalSeconds -ge $inferenceLimit -or $start.Elapsed.TotalSeconds -ge 820) {
                throw 'Four-response qualification exceeded bounded inference window'
            }
            if ($lastObservation.Elapsed.TotalSeconds -ge 10) {
                $observationIndex++
                $allowance = [Math]::Min(30,(Get-RemainingInferenceSeconds -InferenceElapsed $inference.Elapsed.TotalSeconds -OverallElapsed $start.Elapsed.TotalSeconds -Mode $Mode))
                $null = Invoke-MemoryObservationBounded -ContainerId $container -Path (Join-Path $runDir ('memory-{0:d3}.json' -f $observationIndex)) -Phase 'inference' -Seconds $allowance
                $observationCount++
                $lastObservation.Restart()
            }
            $null = $probe.WaitForExit(1000)
        }
        if ($probe.ExitCode -ne 0) { throw "Qualification probe failed ($($probe.ExitCode))" }
        if ($probeClock.Elapsed.TotalSeconds -ge $probeWindow) { throw 'Qualification probe exceeded its deadline' }
        $runtime.Refresh()
        if ($runtime.HasExited) { throw 'Runtime guard stopped before final telemetry' }
        $allowance = [Math]::Min(30,(Get-RemainingInferenceSeconds -InferenceElapsed $inference.Elapsed.TotalSeconds -OverallElapsed $start.Elapsed.TotalSeconds -Mode $Mode))
        $null = Invoke-MemoryObservationBounded -ContainerId $container -Path (Join-Path $runDir 'memory-final.json') -Phase 'final' -Seconds $allowance
        $observationCount++; $finalTelemetry = $true
        $null = Get-RemainingInferenceSeconds -InferenceElapsed $inference.Elapsed.TotalSeconds -OverallElapsed $start.Elapsed.TotalSeconds -Mode $Mode
        }
    } catch { $failure = $_ }
    finally {
        if ($container -notmatch '^[0-9a-f]{64}$') {
            try {
                $recoveryRaw = Invoke-WslBounded -Arguments @('docker','inspect',$name) -Seconds 10
                $recovery = @($recoveryRaw | ConvertFrom-Json -ErrorAction Stop)[0]
                if ($recovery.Id -match '^[0-9a-f]{64}$' -and $recovery.Name -ceq "/$name" -and
                    $recovery.Config.Image -ceq $image -and
                    $recovery.Config.Labels.'strix-alloy.owner' -ceq 'strix-alloy-wsl2' -and
                    $recovery.Config.Labels.'strix-alloy.run' -ceq $name) { $container = $recovery.Id }
                else { throw 'Recovery target does not match this owned create operation' }
            } catch { $cleanupErrors += "create recovery: $_" }
        }
        if ($container -match '^[0-9a-f]{64}$') {
            $preStop = $null; $stopRequested = $false; $stopSucceeded = $false
            try {
                $preStopRaw = Invoke-WslBounded -Arguments @('docker','inspect',$container) -Seconds 15
                [IO.File]::WriteAllText((Join-Path $runDir 'pre-stop-inspect.json'),$preStopRaw + "`n")
                $preStop = @($preStopRaw | ConvertFrom-Json)[0]
                if ($preStop.Id -cne $container -or
                    ($Mode -cne 'PreflightTrace32k' -and (-not $preStop.State.Running -or [int]$preStop.State.Pid -le 0)) -or
                    ($Mode -ceq 'PreflightTrace32k' -and ($preStop.State.Running -or [int]$preStop.State.Pid -ne 0)) -or
                    $preStop.State.OOMKilled -or
                    $null -eq $preStop.State.OOMKilled -or $null -eq $preStop.State.Error -or
                    $preStop.State.Error -or -not $preStop.State.StartedAt) {
                    $cleanupErrors += 'Unexpected pre-stop container termination or error'
                }
                if ($waiter) {
                    $waiter.Refresh()
                    if ($waiter.HasExited -and $Mode -cne 'PreflightTrace32k') { $cleanupErrors += 'Attached start client exited before explicit stop' }
                }
            } catch { $cleanupErrors += "pre-stop inspect: $_" }
            $stopRequested = $true
            try { Invoke-WslBounded -Arguments @('docker','stop','-t','0',$container) -Seconds 45 -CleanupSamples (Join-Path $runDir 'cleanup-memory.jsonl') | Out-Null; $stopSucceeded = $true } catch { $cleanupErrors += "stop: $_" }
            try { Invoke-WslBounded -Arguments @('docker','logs','--timestamps',$container) -Seconds 15 -IncludeStderr | Set-Content -LiteralPath (Join-Path $runDir 'container.log') -Encoding utf8 } catch { $cleanupErrors += "logs: $_" }
            try {
                $inspectRaw = Invoke-WslBounded -Arguments @('docker','inspect',$container) -Seconds 15
                [IO.File]::WriteAllText((Join-Path $runDir 'terminal-inspect.json'),$inspectRaw + "`n")
                $terminal = @($inspectRaw | ConvertFrom-Json)[0]
                $recovered = Get-WindowsAvailableBytes
                Write-RunJson (Join-Path $runDir 'terminal.json') @{id=$container; preStopState=$preStop.State; finalState=$terminal.State;
                    pid=$terminal.State.Pid; running=$terminal.State.Running; exitCode=$terminal.State.ExitCode;
                    oomKilled=$terminal.State.OOMKilled; error=$terminal.State.Error; startedAt=$terminal.State.StartedAt;
                    finishedAt=$terminal.State.FinishedAt; windowsAvailableBytes=$recovered;
                    stopRequested=$stopRequested; stopSucceeded=$stopSucceeded;
                    explicitStop=($stopSucceeded -and $null -ne $preStop -and [bool]$preStop.State.Running -and
                        [int]$preStop.State.Pid -gt 0 -and [int]$terminal.State.ExitCode -in @(0,137,143) -and
                    -not $terminal.State.Error -and $terminal.State.StartedAt -ceq $preStop.State.StartedAt)}
                if ($terminal.Id -cne $container -or $terminal.State.Running -or $terminal.State.Pid -ne 0 -or
                    $terminal.State.OOMKilled -or $null -eq $terminal.State.OOMKilled) { $cleanupErrors += 'Container still running, wrong target, or OOM-killed' }
                if ($null -eq $terminal.State.Error -or $terminal.State.Error -or
                    $null -eq $terminal.State.ExitCode -or
                    ($Mode -cne 'PreflightTrace32k' -and [int]$terminal.State.ExitCode -notin @(0,137,143)) -or
                    -not $terminal.State.StartedAt -or -not $terminal.State.FinishedAt -or
                    ($preStop -and $terminal.State.StartedAt -cne $preStop.State.StartedAt)) {
                    $cleanupErrors += 'Unexpected terminal error, exit code, or container identity'
                }
            } catch { $cleanupErrors += "terminal inspect: $_" }
            if ($Mode -ceq 'PreflightTrace32k') {
                try {
                    $traceEvidence = Assert-PreflightTraceEvidence -LogPath (Join-Path $runDir 'attached-start-stderr.log') -PreStop $preStop -Terminal $terminal -AttachedClient $waiter
                } catch { if ($failure) { $cleanupErrors += "trace evidence: $_" } else { $failure = $_ } }
            }
        }
        foreach ($process in @($probe,$guard,$runtime,$waiter)) {
            if ($null -eq $process) { continue }
            if ($process -eq $waiter) {
                try {
                    $waiter.Refresh()
                    Write-RunJson (Join-Path $runDir 'attached-start-status.json') @{
                        pid=$waiter.Id; exitedBeforeCleanup=$waiter.HasExited;
                        exitCodeBeforeCleanup=if($waiter.HasExited){$waiter.ExitCode}else{$null}}
                } catch { $cleanupErrors += "attached status: $_" }
            }
            try { Stop-QualificationProcess -Process $process -Probe $probe -Mode $Mode } catch { $cleanupErrors += "helper cleanup: $_" }
            try { $process.Dispose() } catch { $cleanupErrors += "helper dispose: $_" }
        }
        try { Write-RunJson (Join-Path $runDir 'outcome.json') @{finishedUtc=[DateTime]::UtcNow.ToString('o'); mode=$Mode; classification=if($Mode -ceq 'PreflightTrace32k'){'diagnostic'}elseif($Mode -ceq 'PreflightServe32k'){'bounded-serving'}else{'qualification'}; traceEvidence=$traceEvidence; failure=if($failure){[string]$failure}else{$null}; cleanupErrors=$cleanupErrors; elapsedSeconds=$start.Elapsed.TotalSeconds; telemetry=@{observationCount=$observationCount; finalCaptured=$finalTelemetry; status=if($Mode -ceq 'PreflightTrace32k'){'not-applicable'}elseif($finalTelemetry -and $observationCount -ge 2){'complete'}else{'failed'}}} }
        catch { $cleanupErrors += "outcome write: $_" }
    }
    if ($failure -and $cleanupErrors.Count) { throw "Primary failure: $failure; cleanup/telemetry failures: $($cleanupErrors -join '; ')" }
    if ($failure) { throw $failure }
    if ($cleanupErrors.Count) { throw ($cleanupErrors -join '; ') }
    if ($Mode -ceq 'PreflightTrace32k') { Write-Output "DIAGNOSTIC $container $runDir" }
    elseif ($Mode -ceq 'PreflightServe32k') { Write-Output "SERVED bounded session $container $runDir" }
    else { Write-Output "QUALIFIED $container $runDir" }
}

if ($MyInvocation.InvocationName -ne '.') { Invoke-Qualification -Mode $Mode }
