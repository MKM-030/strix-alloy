param([Parameter(Mandatory)][string]$ContainerId, [Parameter(Mandatory)][string]$Output, [Parameter(Mandatory)][ValidateSet('ready','inference','final')][string]$Phase, [Parameter(Mandatory)][ValidatePattern('^[A-Za-z0-9_][A-Za-z0-9_.-]*$')][string]$Distribution, [Parameter(Mandatory)][ValidatePattern('^[A-Za-z0-9_][A-Za-z0-9_.-]*$')][string]$LinuxUser)
$ErrorActionPreference='Stop'
if ($ContainerId -notmatch '^[0-9a-f]{64}$') { throw 'Exact container ID required' }
$results=Split-Path -Parent $Output
$wslArgs=@('-d',$Distribution,'-u',$LinuxUser,'--exec')
# Portable boundaries used by the frozen controller copy. No shell interpolation.
function ConvertTo-NativeArgument([string]$Value) {
    if($Value.Length -gt 0 -and $Value -notmatch '[\s"]'){return $Value}
    '"' + [regex]::Replace([regex]::Replace($Value, '(\\*)"', '$1$1\"'), '(\\+)$', '$1$1') + '"'
}

function Start-PortableProcess {
    param([string]$FilePath, [string]$WindowStyle, [switch]$PassThru,
          [string[]]$ArgumentList, [string]$RedirectStandardOutput, [string]$RedirectStandardError)
    foreach($path in @($RedirectStandardOutput,$RedirectStandardError)) {
        if($path -and (Test-Path -LiteralPath $path)){throw "Refusing to overwrite helper output: $path"}
    }
    $quoted=@($ArgumentList | ForEach-Object { ConvertTo-NativeArgument $_ })
    Start-Process -FilePath $FilePath -WindowStyle Hidden -PassThru -ArgumentList $quoted `
        -RedirectStandardOutput $RedirectStandardOutput -RedirectStandardError $RedirectStandardError
}

function Stop-HelperChecked($Process) {
    $Process.Refresh()
    if (-not $Process.HasExited) {
        # The retained Process object belongs to this directly started WSL
        # helper. .NET Framework has Kill(), without the newer tree overload.
        $Process.Kill()
        if (-not $Process.WaitForExit(10000)) { throw 'Killed helper did not terminate within 10 seconds' }
        $Process.Refresh()
        if (-not $Process.HasExited) { throw 'Killed helper did not terminate within 10 seconds' }
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
        # Retain the native handle before waiting: Windows PowerShell 5.1's
        # Start-Process otherwise loses ExitCode when a short helper exits.
        $null = $p.Handle
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
    $guestRaw = Invoke-WslBounded -Arguments @('docker','exec',$ContainerId,'python3','/candidate/startup_cache.py','--memory-only') -Seconds 5
    $guestSnapshot = $guestRaw | ConvertFrom-Json -ErrorAction Stop
    if ($guestSnapshot.schema -cne 'startup-cache-cgroup-memory-v1' -or
        [string]$guestSnapshot.cgroup_path -notmatch '^/') { throw 'Invalid exact-cgroup memory telemetry' }
    $guest['cgroupPath'] = [string]$guestSnapshot.cgroup_path
    foreach ($metric in @('memory.current','memory.peak','memory.swap.current')) {
        $value = [string]$guestSnapshot.$metric
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
$record=Write-MemoryObservation -ContainerId $ContainerId -Path $Output -Phase $Phase
if ($record.windows.availableBytes -lt 12GB -or ($record.windows.commitLimitBytes-$record.windows.committedBytes) -lt 12GB) { throw 'Memory observation crossed retained floor' }
