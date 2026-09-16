#requires -Version 5.1
<#
.SYNOPSIS
Diagnose (and optionally repair) the broken native-Windows ROCm/HIP path.
.DESCRIPTION
Read-only by default. Facts established so far:
  * GPU device healthy (CM_PROB_NONE), driver version unchanged (32.0.31041.1004)
  * Vulkan works; WSL HIP works; native-Windows HIP fails with
    "cudaMemGetInfo failed (invalid argument), returning 0/0"
  => the GPU and the kernel driver are fine; the native ROCm user-mode component is not.
This script checks the remaining suspects and can restart the adapter.

  .\repair-gpu.ps1                     # read-only diagnosis (elevated)
  .\repair-gpu.ps1 -RestartAdapter     # + restart the display device (brief screen flash)
#>
[CmdletBinding()]
param([switch]$RestartAdapter)
$ErrorActionPreference = 'Continue'
$res = 'C:\Projects\REV-N-ornith-eval-20260911\kernel-work\results'
New-Item -ItemType Directory -Path $res -Force | Out-Null

function Is-Admin {
    $id = [Security.Principal.WindowsIdentity]::GetCurrent()
    (New-Object Security.Principal.WindowsPrincipal($id)).IsInRole(
        [Security.Principal.WindowsBuiltInRole]::Administrator)
}
function ReadShared([string]$p) {
    if (-not (Test-Path -LiteralPath $p)) { return '' }
    try {
        $fs = [IO.File]::Open($p, [IO.FileMode]::Open, [IO.FileAccess]::Read, [IO.FileShare]::ReadWrite)
        $sr = New-Object IO.StreamReader($fs); $t = $sr.ReadToEnd(); $sr.Close(); $fs.Close(); return $t
    } catch { return '' }
}

Write-Output "Elevated = $(Is-Admin)   (RestartAdapter requested = $RestartAdapter)"
$os = Get-CimInstance Win32_OperatingSystem
Write-Output "Booted   = $($os.LastBootUpTime.ToString('o'))   uptime = $((Get-Date) - $os.LastBootUpTime)"
Write-Output ''

Write-Output '=== 1. GPU hang reports (Kernel_141 = LiveKernelEvent 141, GPU hang) ==='
$q = 'C:\ProgramData\Microsoft\Windows\WER\ReportQueue'
$dirs = @()
if (Test-Path $q) {
    $dirs = Get-ChildItem $q -Directory -ErrorAction SilentlyContinue |
            Where-Object { $_.Name -match '^Kernel_141' } | Sort-Object LastWriteTime -Descending | Select-Object -First 2
}
if (-not $dirs) { Write-Output '  none present' }
foreach ($d in $dirs) {
    Write-Output "  --- $($d.Name) ---"
    $t = ReadShared (Join-Path $d.FullName 'Report.wer')
    if (-not $t) { Write-Output '      (unreadable - needs admin)' }
    else {
        foreach ($ln in ($t -split "`n")) {
            if ($ln -match '^(EventType|EventTime|AppName|Response\.|ReportDescription|Sig\[0|DynamicSig\[1\d)') {
                Write-Output ("      " + $ln.Trim())
            }
        }
    }
}

Write-Output ''
Write-Output '=== 2. device problem codes (adapter + NPU + anything else) ==='
foreach ($d in (Get-PnpDevice -PresentOnly -ErrorAction SilentlyContinue |
                Where-Object { $_.Class -in @('Display','ComputeAccelerator') })) {
    Write-Output ("  [{0}] {1}  problem={2}  status={3}" -f $d.Status, $d.FriendlyName, $d.Problem, $d.Status)
}
$bad = Get-PnpDevice -PresentOnly -ErrorAction SilentlyContinue |
       Where-Object { $_.Problem -ne 'CM_PROB_NONE' }
if ($bad) {
    Write-Output '  --- devices with a problem code ---'
    foreach ($b in $bad) { Write-Output ("      [{0}] {1} problem={2}" -f $b.Status, $b.FriendlyName, $b.Problem) }
} else { Write-Output '  (no device has a problem code)' }

Write-Output ''
Write-Output '=== 3. driver load / PnP events since the last boot ==='
try {
    Get-WinEvent -FilterHashtable @{ LogName='System'; StartTime=$os.LastBootUpTime } -ErrorAction Stop |
        Where-Object { $_.ProviderName -match 'Kernel-PnP|DriverFrameworks|Display|amdkmdag|WUDFRd' -or $_.Message -match 'WUDFRd' } |
        Select-Object -First 20 |
        ForEach-Object { Write-Output ("  {0} [{1}] id={2} : {3}" -f $_.TimeCreated.ToString('HH:mm:ss'), $_.ProviderName, $_.Id, (($_.Message -split "`n")[0]).Trim()) }
} catch { Write-Output "  (none / query failed)" }

Write-Output ''
Write-Output '=== 4. adapter memory as reported (multiple sources) ==='
$gpu = Get-CimInstance Win32_VideoController -ErrorAction SilentlyContinue |
       Where-Object { $_.Name -match 'Radeon' } | Select-Object -First 1
if ($gpu) {
    Write-Output ("  Name={0}" -f $gpu.Name)
    Write-Output ("  DriverVersion={0}  DriverDate={1}" -f $gpu.DriverVersion, $gpu.DriverDate)
    Write-Output ("  AdapterRAM (legacy, unreliable on UMA)= {0} bytes" -f $gpu.AdapterRAM)
    Write-Output ("  VideoProcessor={0}" -f $gpu.VideoProcessor)
    Write-Output ("  Status={0}  ConfigManagerErrorCode={1}" -f $gpu.Status, $gpu.ConfigManagerErrorCode)
}
Write-Output '  --- AMD driver registry keys ---'
foreach ($k in @('HKLM:\SYSTEM\CurrentControlSet\Control\Class\{4d36e968-e325-11ce-bfc1-08002be10318}\0000',
                 'HKLM:\SYSTEM\CurrentControlSet\Control\Class\{4d36e968-e325-11ce-bfc1-08002be10318}\0001')) {
    if (Test-Path $k) {
        $p = Get-ItemProperty $k -ErrorAction SilentlyContinue
        Write-Output ("    {0}: DriverVersion={1}  ProviderName={2}" -f (Split-Path $k -Leaf), $p.DriverVersion, $p.ProviderName)
        foreach ($n in @('HardwareInformation.DedicatedVideoMemory','HardwareInformation.qwMemorySize','HardwareInformation.MemorySize')) {
            if ($p.PSObject.Properties[$n]) {
                $v = $p.$n
                if ($v -is [byte[]]) { $v = [BitConverter]::ToUInt64(($v + (New-Object byte[] 8))[0..7], 0) }
                Write-Output ("        {0} = {1}" -f $n, $v)
            }
        }
    }
}

Write-Output ''
Write-Output '=== 5. Windows performance counters for the adapter (if any) ==='
try {
    Get-Counter -ListSet 'GPU Adapter Memory' -ErrorAction Stop | Out-Null
    (Get-Counter '\GPU Adapter Memory(*)\Dedicated Usage' -ErrorAction SilentlyContinue).CounterSamples |
        Select-Object -First 8 |
        ForEach-Object { Write-Output ("  {0} = {1:N0}" -f $_.InstanceName, $_.CookedValue) }
} catch { Write-Output '  (GPU counters unavailable)' }

if ($RestartAdapter) {
    Write-Output ''
    Write-Output '=== 6. RESTARTING THE DISPLAY ADAPTER ==='
    if (-not (Is-Admin)) { Write-Output '  need elevation - skipped'; return }
    if (-not $gpu) { Write-Output '  no adapter found - skipped'; return }
    $inst = (Get-PnpDevice -PresentOnly | Where-Object { $_.FriendlyName -match 'Radeon' } | Select-Object -First 1).InstanceId
    Write-Output "  instance = $inst"
    Write-Output '  running: pnputil /restart-device'
    $o = (& pnputil /restart-device "$inst" 2>&1 | Out-String)
    Write-Output ("  exit=$LASTEXITCODE")
    foreach ($ln in ($o -split "`n")) { if ($ln.Trim()) { Write-Output ("    " + $ln.Trim()) } }
    Write-Output '  waiting 20s for the adapter to settle...'
    Start-Sleep -Seconds 20
    Write-Output '  retest with:  .\gpu-probe.ps1'
}
