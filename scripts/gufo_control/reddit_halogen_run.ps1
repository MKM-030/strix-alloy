<# Private one-attempt Halogen Reddit replay. Validate is offline; run requires a
   source-bound independent review and a completed native table. No public file
   or system configuration is changed. #>
param([Parameter(Mandatory)][ValidateSet('validate','run')][string]$Action,
      [Parameter(Mandatory)][ValidateSet('mixed','repetitive')][string]$Table,
      [Parameter(Mandatory)][string]$NativeResult,
      [switch]$UserWaivePhysicalStartEstimate)
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'reddit_halogen_controller.ps1')
$research = 'C:\Projects\strix-alloy-research'
$wsl = 'C:\Projects\strix-alloy-wsl2'
$guardScript = Join-Path $PSScriptRoot 'reddit_halogen_startup_guard.py'
$evidence = Join-Path $research "reports\reddit-halogen-$Table-20260928-v6-runs"
$reviewPath = Join-Path $research "reports\reddit-halogen-$Table-20260928-v6-review.json"
$clientModule = 'integration.scripts.gufo_control.reddit_halogen_client'
$guardArgs = @('--distro','Ubuntu-24.04','--user','revn',
    '--models','/mnt/halogen-wsl-ext4/models','--workspace','/mnt/c/Users/Marcel/Documents/Codex/2026-08-25/goal-ermittle-und-implementiere-auf-meinem',
    '--dxg','/home/revn/ciru-runtime/venv/lib/python3.14/site-packages/_rocm_sdk_devel/lib/librocdxg.so')

function Quote-Argument([string]$Value) {
    if ($Value.Length -gt 0 -and $Value -notmatch '[\s"]') { return $Value }
    return '"' + [regex]::Replace([regex]::Replace($Value, '(\\*)"', '$1$1\"'), '(\\+)$', '$1$1') + '"'
}
function Start-PrivateProcess([string]$File, [string[]]$Arguments, [string]$Out, [string]$Err) {
    foreach ($path in @($Out,$Err)) { if (Test-Path -LiteralPath $path) { throw "Output already exists: $path" } }
    $quoted = @($Arguments | ForEach-Object { Quote-Argument $_ })
    return Start-Process -FilePath $File -WindowStyle Hidden -PassThru -ArgumentList $quoted `
        -WorkingDirectory $research -RedirectStandardOutput $Out -RedirectStandardError $Err
}
function Get-MemoryFrame {
    if (-not ('RedditHalogenDirectMemory' -as [type])) {
        Add-Type -TypeDefinition @'
using System;
using System.ComponentModel;
using System.Runtime.InteropServices;
public static class RedditHalogenDirectMemory {
    [StructLayout(LayoutKind.Sequential)] private struct M {
        public uint Length, Load;
        public ulong TotalPhys, AvailPhys, TotalPageFile, AvailPageFile;
        public ulong TotalVirtual, AvailVirtual, AvailExtendedVirtual;
    }
    [StructLayout(LayoutKind.Sequential)] private struct P {
        public uint Length;
        public UIntPtr CommitTotal, CommitLimit, CommitPeak, PhysicalTotal, PhysicalAvailable,
            SystemCache, KernelTotal, KernelPaged, KernelNonpaged, PageSize;
        public uint HandleCount, ProcessCount, ThreadCount;
    }
    [DllImport("kernel32.dll", SetLastError=true)] private static extern bool GlobalMemoryStatusEx(ref M m);
    [DllImport("psapi.dll", SetLastError=true)] private static extern bool GetPerformanceInfo(ref P p, uint size);
    public static long[] Read() {
        M m = new M(); P p = new P();
        m.Length = (uint)Marshal.SizeOf<M>(); p.Length = (uint)Marshal.SizeOf<P>();
        if (!GlobalMemoryStatusEx(ref m)) throw new Win32Exception(Marshal.GetLastWin32Error());
        if (!GetPerformanceInfo(ref p,p.Length)) throw new Win32Exception(Marshal.GetLastWin32Error());
        long page = checked((long)p.PageSize.ToUInt64());
        return new long[] { checked((long)m.AvailPhys),
            checked((long)p.CommitTotal.ToUInt64() * page),
            checked((long)p.CommitLimit.ToUInt64() * page) };
    }
}
'@
    }
    $v = [RedditHalogenDirectMemory]::Read()
    return @{ utc=[DateTime]::UtcNow.ToString('o'); availableBytes=$v[0];
        committedBytes=$v[1]; commitLimitBytes=$v[2];
        commitHeadroomBytes=($v[2]-$v[1]); source='direct_global_memory_status_and_performance_info' }
}
function Check-Floors([string]$Log) {
    $frame = Get-MemoryFrame
    if ($Log) { ($frame | ConvertTo-Json -Compress) | Add-Content -LiteralPath $Log -Encoding utf8 }
    if ($frame.availableBytes -lt 12GB) { throw 'Windows available below user-authorized 12 GiB floor' }
    if ($frame.commitHeadroomBytes -lt 12GB) { throw 'Windows commit headroom below 12 GiB retained floor' }
    return $frame
}
function Assert-HostHeartbeat([string]$Log, $Process) {
    if ($null -eq $Process) { throw 'Supplemental guard missing' }
    $Process.Refresh()
    if ($Process.HasExited) { throw 'Supplemental guard exited before cleanup release' }
    if (-not (Test-Path -LiteralPath $Log)) { throw 'Supplemental guard telemetry missing' }
    $latest = @(Get-Content -LiteralPath $Log -Tail 8 | ForEach-Object {
        try { $_ | ConvertFrom-Json -ErrorAction Stop } catch { $null }
    } | Where-Object { $_.event -eq 'sample' }) | Select-Object -Last 1
    if ($null -eq $latest -or -not $latest.utc) { throw 'Supplemental guard has no sample' }
    # PowerShell may deserialize ISO JSON timestamps directly into DateTime.
    # Do not stringify that value with one culture and parse with another.
    $sampleUtc = if ($latest.utc -is [DateTime]) { $latest.utc.ToUniversalTime() }
        elseif ($latest.utc -is [DateTimeOffset]) { $latest.utc.UtcDateTime }
        else { [DateTimeOffset]::Parse([string]$latest.utc, [Globalization.CultureInfo]::InvariantCulture).UtcDateTime }
    $age = ([DateTime]::UtcNow - $sampleUtc).TotalSeconds
    if ($age -lt -5 -or $age -gt 6 -or [int64]$latest.available_bytes -lt 12GB -or
        [int64]$latest.commit_headroom_bytes -lt 12GB) { throw 'Supplemental guard heartbeat stale or unsafe' }
}
function Get-WindowsLaunchReserve {
    $frame = Check-Floors ''
    if ($frame.availableBytes -lt $script:admissionMinBytes) { throw 'Fresh physical admission below reviewed scenario' }
    if ($frame.commitHeadroomBytes -lt ($script:plannedCommitGrowthBytes + 12GB)) {
        throw 'Fresh commit admission below reviewed growth plus 12 GiB floor'
    }
    return $frame.availableBytes
}
function Get-ReviewPlan {
    Push-Location $research
    try {
        $raw = & $python -B -m $clientModule validate --table $Table --source $NativeResult
        if ($LASTEXITCODE -ne 0) { throw 'Offline frozen workload validation failed' }
        $plan = $raw | ConvertFrom-Json -ErrorAction Stop
    } finally { Pop-Location }
    return $plan
}
function Assert-NoNativeEngine {
    $processes = @(Get-CimInstance Win32_Process -ErrorAction Stop)
    if (@($processes | Where-Object { $_.Name -match '^(nativeengine|gufo|llama-server)(\.exe)?$' }).Count) {
        throw 'Native GPU engine still active'
    }
}
function Assert-Review($Plan) {
    if (-not (Test-Path -LiteralPath $reviewPath -PathType Leaf)) { throw "Independent review missing: $reviewPath" }
    $r = Get-Content -LiteralPath $reviewPath -Raw | ConvertFrom-Json -ErrorAction Stop
    $nominal = 55029268480L # reviewed 51.25 GiB direct-C1 scenario
    if ($r.decision -cne 'approved' -or $r.binding_sha256 -cne $Plan.binding_sha256 -or
        [int64]$r.admission_min_bytes -lt $nominal -or
        [int64]$r.planned_commit_growth_bytes -lt 86GB -or -not $r.allocation_reason -or
        [int64]$r.runtime_physical_floor_bytes -ne 12GB -or
        $r.runtime_physical_floor_authorization -cne 'Ja von 24 auf 12') {
        throw 'Independent binding or allocation review invalid'
    }
    $script:admissionMinBytes = [int64]$r.admission_min_bytes
    $script:plannedCommitGrowthBytes = [int64]$r.planned_commit_growth_bytes
    if ($UserWaivePhysicalStartEstimate) {
        if ($r.physical_start_waiver_authorization -cne 'Ignorier die Grenze mach weiter') {
            throw 'Explicit user authorization for physical start estimate waiver missing'
        }
        # User-authorized empirical attempt, not a revised allocation estimate.
        # Keep 24 GiB minimum at launch; separately authorized runtime floor is 12 GiB.
        # The 86+12 GiB commit admission is unchanged.
        $script:admissionMinBytes = 24GB
    }
    return $r
}
function New-RedditArguments($Reference, $Admission, [string]$Name) {
    $base = New-RunArguments $Reference $Admission $Name -Mode 'PreflightPinned32k'
    if ($base.Count -eq 1 -and $base[0] -is [array]) { $base = $base[0] }
    $fixed = @{
        HALOGEN_CTX='133888'; HALOGEN_KV_POOL_POSITIONS='133888'; HALOGEN_KV_SLOTS='1';
        HALOGEN_PROMPT_CACHE='2'; HALOGEN_PREFILL_CHUNK='2048'; HALOGEN_MAX_TOK='2048';
        HALOGEN_CACHE_BRANCHES='2'; HALOGEN_CACHE_INPLACE='1'; HALOGEN_CACHE_SNAP3='0';
        HALOGEN_CACHE_FULL='0'; HALOGEN_CACHE_ENTRIES='3'
    }
    $args = [Collections.Generic.List[string]]::new()
    foreach ($part in $base) { $args.Add([string]$part) }
    $seen = @{}
    for ($i=0; $i -lt $args.Count-1; $i++) {
        if ($args[$i] -eq '--env') {
            $key = ($args[$i+1] -split '=',2)[0]
            if ($seen.ContainsKey($key)) { throw "Duplicate environment key: $key" }
            $seen[$key] = $true
            if ($fixed.ContainsKey($key)) { $args[$i+1] = "$key=$($fixed[$key])" }
        }
    }
    if ($seen['HALOGEN_CHECKPOINT'] -ne $true -or $seen['HALOGEN_TOKENIZER'] -ne $true -or
        @($args | Where-Object { $_ -ceq 'HALOGEN_CHECKPOINT=/models/qwen38-flash-next-w4b.hgn' }).Count -ne 1 -or
        @($args | Where-Object { $_ -ceq 'HALOGEN_TOKENIZER=/models/tokenizer' }).Count -ne 1) {
        throw 'Pinned HGN or tokenizer selection missing'
    }
    $imageIndex = $args.IndexOf($image)
    $entryIndex = $args.IndexOf('--entrypoint')
    if ($imageIndex -lt 0 -or $entryIndex -lt 0 -or $args[$imageIndex+3] -cne '900s') {
        throw 'Unexpected base container entrypoint'
    }
    $args[$imageIndex+3] = '4100s'
    foreach ($key in $fixed.Keys) {
        if (-not $seen.ContainsKey($key)) {
            $args.Insert($entryIndex, '--env'); $entryIndex++
            $args.Insert($entryIndex, "$key=$($fixed[$key])"); $entryIndex++
        }
    }
    $args.Insert(3, '--label'); $args.Insert(4, 'strix-alloy.owner=strix-alloy-wsl2')
    $args.Insert(5, '--label'); $args.Insert(6, "strix-alloy.run=$Name")
    return ,$args.ToArray()
}
function Start-MemorySample([string]$Container, [string]$RunDir, [int]$Index, [string]$Phase) {
    $path = Join-Path $RunDir ('memory-{0:d3}.json' -f $Index)
    $p = Start-PrivateProcess $pwsh @('-NoProfile','-File',(Join-Path $PSScriptRoot 'reddit_halogen_sample.ps1'),
        '-ContainerId',$Container,'-Output',$path,'-Phase',$Phase) `
        (Join-Path $RunDir ('sample-{0:d3}.stdout.log' -f $Index)) `
        (Join-Path $RunDir ('sample-{0:d3}.stderr.log' -f $Index))
    return @{process=$p; path=$path; phase=$Phase}
}
function Finish-Sample($Sample, [string]$Container) {
    if ($null -eq $Sample) { return }
    $p = $Sample.process
    $p.Refresh()
    if (-not $p.HasExited) { throw "Memory sample worker did not finish: $($Sample.path)" }
    if ($p.ExitCode -ne 0) { throw "Memory sample worker failed: $($Sample.path)" }
    $null = Assert-MemoryArtifact -ContainerId $Container -Path $Sample.path -Phase $Sample.phase
    $p.Dispose()
}

$plan = Get-ReviewPlan
if ($Action -eq 'validate') { $plan | ConvertTo-Json -Depth 20; return }
$review = Assert-Review $plan
if (Test-Path -LiteralPath (Join-Path $evidence 'attempt.json')) { throw 'One table attempt already consumed' }
Assert-NoNativeEngine
$admission = Assert-Admission -Mode 'PreflightPinned32k'
$reference = @(Get-Content -LiteralPath (Join-Path $root 'results\halogen-performance-20260924\publication-repeat3-inspect.json') -Raw | ConvertFrom-Json)[0]
$stamp = [DateTime]::UtcNow.ToString('yyyyMMddTHHmmssZ')
$nonce = [guid]::NewGuid().ToString('N')
$name = "halogen-flash-hybrid-reddit-$Table-$nonce"
$runDir = Join-Path $evidence "$stamp-$nonce"
$argsRun = New-RedditArguments $reference $admission $name
New-Item -ItemType Directory -Path $evidence -Force -ErrorAction Stop | Out-Null
New-Item -ItemType Directory -Path $runDir -ErrorAction Stop | Out-Null
Write-RunJson (Join-Path $evidence 'attempt.json') @{table=$Table; run=$runDir; binding_sha256=$plan.binding_sha256}
Write-RunJson (Join-Path $runDir 'manifest.json') @{plan=$plan; review=$review; admission=$admission; args=$argsRun;
    physical_start_estimate_waived=[bool]$UserWaivePhysicalStartEstimate;
    effective_physical_admission_bytes=$script:admissionMinBytes}
$container = $null; $attached = $null; $startupGuard = $null; $runtimeGuard = $null; $hostGuard = $null
$client = $null; $sample = $null; $sampleCount = 0; $failure = $null; $cleanupErrors = @()
$ledgerAuditPassed = $false
$clock = [Diagnostics.Stopwatch]::StartNew()
$monitor = Join-Path $runDir 'windows-memory.jsonl'
try {
    if ((Get-ReviewPlan).binding_sha256 -cne $plan.binding_sha256) {
        throw 'Source or implementation changed after independent review'
    }
    $fresh = Check-Floors $monitor
    if ($fresh.availableBytes -lt $admissionMinBytes -or
        $fresh.commitHeadroomBytes -lt ($plannedCommitGrowthBytes + 12GB)) {
        throw 'Final immediate precreate admission failed'
    }
    Write-RunJson (Join-Path $runDir 'precreate.json') $fresh
    Assert-NoNativeEngine
    $container = Invoke-WslBounded -Arguments (@('docker') + $argsRun) -Seconds 30
    if ($container -notmatch '^[0-9a-f]{64}$') { throw 'Invalid created container ID' }
    Write-RunJson (Join-Path $runDir 'container-id.json') @{id=$container; name=$name}
    $hostLog = Join-Path $runDir 'host-guard.jsonl'
    $releasePath = Join-Path $runDir 'host-guard-release.json'
    $hostGuard = Start-PrivateProcess $python @('-B',(Join-Path $PSScriptRoot 'reddit_halogen_host_guard.py'),
        '--container-id',$container,'--output',$hostLog,'--release',$releasePath) `
        (Join-Path $runDir 'host-guard.stdout.log') (Join-Path $runDir 'host-guard.stderr.log')
    $armedClock = [Diagnostics.Stopwatch]::StartNew()
    while ($armedClock.Elapsed.TotalSeconds -lt 20) {
        $null = Check-Floors $monitor
        $hostGuard.Refresh()
        if ($hostGuard.HasExited) { throw 'Supplemental host guard failed before handoff' }
        if ((Test-Path -LiteralPath $hostLog) -and
            ((Get-Content -LiteralPath $hostLog -Tail 3) -match '"event":\s*"armed"')) { break }
        Start-Sleep -Milliseconds 200
    }
    if ($armedClock.Elapsed.TotalSeconds -ge 20) { throw 'Supplemental host guard handoff deadline' }
    Assert-HostHeartbeat $hostLog $hostGuard
    $attached = Start-PrivateProcess 'wsl.exe' ($wslArgs + @('docker','start','-a',$container)) `
        (Join-Path $runDir 'attached.stdout.log') (Join-Path $runDir 'attached.stderr.log')
    while ($clock.Elapsed.TotalSeconds -lt 420) {
        $null = Check-Floors $monitor
        Assert-HostHeartbeat $hostLog $hostGuard
        $attached.Refresh()
        if ($attached.HasExited) { throw 'Attached start exited before running' }
        $state = Invoke-WslBounded -Arguments @('docker','inspect','--format','{{.Id}}|{{.State.Running}}',$container) -Seconds 5
        if ($state -ceq "$container|true") { break }
        if ($state -cne "$container|false") { throw 'Unexpected container start state' }
        Start-Sleep -Milliseconds 250
    }
    if ($clock.Elapsed.TotalSeconds -ge 420) { throw 'Container start deadline' }
    $startupGuard = Start-PrivateProcess $python (@('-B',$guardScript,'--container-id',$container,
        '--output',(Join-Path $runDir 'startup-guard.jsonl')) + $guardArgs) `
        (Join-Path $runDir 'startup-guard.stdout.log') (Join-Path $runDir 'startup-guard.stderr.log')
    while ($clock.Elapsed.TotalSeconds -lt 420) {
        $null = Check-Floors $monitor
        Assert-HostHeartbeat $hostLog $hostGuard
        $startupGuard.Refresh()
        if ($startupGuard.HasExited) { break }
        Start-Sleep -Seconds 1
    }
    if (-not $startupGuard.HasExited -or $startupGuard.ExitCode -ne 0) { throw 'Startup guard rejected or timed out' }
    $runtimeStarted = [DateTime]::UtcNow
    $runtimeLog = Join-Path $runDir 'runtime-guard.jsonl'
    $runtimeGuard = Start-PrivateProcess $python (@('-B',$guardScript,'--container-id',$container,
        '--output',$runtimeLog,'--runtime-seconds','3600') + $guardArgs) `
        (Join-Path $runDir 'runtime-guard.stdout.log') (Join-Path $runDir 'runtime-guard.stderr.log')
    Wait-LookupRuntimeGuard -Process $runtimeGuard -LogPath $runtimeLog -ContainerId $container `
        -NotBeforeUtc $runtimeStarted -DurationSeconds 3600 -TimeoutSeconds 30 `
        -MemoryCheck { $null = Check-Floors $monitor; Assert-HostHeartbeat $hostLog $hostGuard }
    $sample = Start-MemorySample $container $runDir $sampleCount 'ready'
    $sampleCount++
    $client = Start-PrivateProcess $python @('-B','-m',$clientModule,'replay','--table',$Table,
        '--source',$NativeResult,'--container',$container,'--output',(Join-Path $runDir 'replay.json')) `
        (Join-Path $runDir 'client.stdout.log') (Join-Path $runDir 'client.stderr.log')
    $lastSample = [Diagnostics.Stopwatch]::StartNew()
    while ($clock.Elapsed.TotalSeconds -lt 4050) {
        $null = Check-Floors $monitor
        Assert-HostHeartbeat $hostLog $hostGuard
        $runtimeGuard.Refresh(); $client.Refresh()
        if ($runtimeGuard.HasExited) { throw 'Runtime guard stopped before replay finished' }
        if ($sample) {
            $sample.process.Refresh()
            if ($sample.process.HasExited) { Finish-Sample $sample $container; $sample = $null }
        }
        if ($client.HasExited) { break }
        if (-not $sample -and $lastSample.Elapsed.TotalSeconds -ge 10) {
            $sample = Start-MemorySample $container $runDir $sampleCount 'inference'
            $sampleCount++; $lastSample.Restart()
        }
        Start-Sleep -Seconds 1
    }
    if (-not $client.HasExited -or $client.ExitCode -ne 0) { throw 'Replay client failed or exceeded run deadline' }
    while ($sample -and -not $sample.process.HasExited -and $clock.Elapsed.TotalSeconds -lt 4080) {
        $null = Check-Floors $monitor; Start-Sleep -Seconds 1; $sample.process.Refresh()
    }
    if ($sample) { Finish-Sample $sample $container; $sample = $null }
    $sample = Start-MemorySample $container $runDir $sampleCount 'final'
    while (-not $sample.process.HasExited -and $clock.Elapsed.TotalSeconds -lt 4080) {
        $null = Check-Floors $monitor; Start-Sleep -Seconds 1; $sample.process.Refresh()
    }
    Finish-Sample $sample $container; $sample = $null; $sampleCount++
} catch { $failure = [string]$_ }
finally {
    if ($container -notmatch '^[0-9a-f]{64}$') {
        try {
            $recovered = Invoke-WslBounded -Arguments @('docker','inspect','--format','{{.Id}}',$name) -Seconds 10
            if ($recovered -match '^[0-9a-f]{64}$') { $container = $recovered }
        } catch { $cleanupErrors += "named create recovery: $_" }
    }
    if ($container -match '^[0-9a-f]{64}$') {
        $wasRunning = $false; $before = $null
        try {
            $raw = Invoke-WslBounded -Arguments @('docker','inspect',$container) -Seconds 15
            [IO.File]::WriteAllText((Join-Path $runDir 'pre-stop-inspect.json'),$raw)
            $before = @($raw | ConvertFrom-Json)[0]
            if ($before.Id -cne $container -or $before.Name -cne "/$name") { throw 'Pre-stop identity changed' }
            $wasRunning = [bool]$before.State.Running
        } catch { $cleanupErrors += "pre-stop inspect: $_" }
        if ($wasRunning -or $null -eq $before) {
            try { Invoke-WslBounded -Arguments @('docker','stop','-t','0',$container) -Seconds 45 `
                    -CleanupSamples (Join-Path $runDir 'cleanup-memory.jsonl') | Out-Null }
            catch { $cleanupErrors += "exact-container stop: $_" }
        }
        try {
            $raw = Invoke-WslBounded -Arguments @('docker','inspect',$container) -Seconds 15
            [IO.File]::WriteAllText((Join-Path $runDir 'terminal-inspect.json'),$raw)
            $state = @($raw | ConvertFrom-Json)[0]
            if ($state.Id -cne $container -or $state.State.Running -or $state.State.Pid -ne 0 -or
                $state.State.OOMKilled -or $state.State.Error) { $cleanupErrors += 'Terminal state unsafe' }
        } catch { $cleanupErrors += "terminal inspect: $_" }
        try { Invoke-WslBounded -Arguments @('docker','logs','--timestamps',$container) -Seconds 15 -IncludeStderr |
                Set-Content -LiteralPath (Join-Path $runDir 'container.log') -Encoding utf8 }
        catch { $cleanupErrors += "container logs: $_" }
        if (-not $failure -and -not $cleanupErrors.Count) {
            try {
                Push-Location $research
                try {
                    & $python -B -m $clientModule audit --table $Table --source $NativeResult `
                        --replay (Join-Path $runDir 'replay.json') --log (Join-Path $runDir 'container.log') `
                        --output (Join-Path $runDir 'ledger-audit.json')
                    $ledgerAuditPassed = ($LASTEXITCODE -eq 0)
                } finally { Pop-Location }
                if (-not $ledgerAuditPassed) { $cleanupErrors += 'Serving ledger audit failed' }
            } catch { $cleanupErrors += "serving ledger audit: $_" }
        }
    }
    if ($hostGuard) {
        try {
            Assert-HostHeartbeat $hostLog $hostGuard
            Write-RunJson $releasePath @{utc=[DateTime]::UtcNow.ToString('o'); container=$container;
                phase='terminal_inspection_and_logs_complete'}
            if (-not $hostGuard.WaitForExit(15000) -or $hostGuard.ExitCode -ne 0) {
                throw 'Supplemental guard did not release cleanly'
            }
        } catch { $cleanupErrors += "supplemental host guard cleanup: $_" }
    }
    foreach ($process in @($sample.process,$client,$startupGuard,$runtimeGuard,$hostGuard,$attached)) {
        if ($null -eq $process) { continue }
        try { Stop-HelperChecked $process -Tree; $process.Dispose() }
        catch { $cleanupErrors += "owned helper cleanup: $_" }
    }
    try { $null = Check-Floors $monitor } catch { $cleanupErrors += "final memory: $_" }
    Write-RunJson (Join-Path $runDir 'outcome.json') @{table=$Table; source=$NativeResult;
        binding_sha256=$plan.binding_sha256; container=$container; failure=$failure;
        cleanup_errors=$cleanupErrors; elapsed_seconds=$clock.Elapsed.TotalSeconds;
        samples=$sampleCount; replay=(Join-Path $runDir 'replay.json');
        ledger_audit=(Join-Path $runDir 'ledger-audit.json'); comparable_success=$ledgerAuditPassed}
}
if ($failure -or $cleanupErrors.Count) { throw "Replay failure: $failure; cleanup: $($cleanupErrors -join '; ')" }
Write-Output "DONE $runDir"
