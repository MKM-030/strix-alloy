#requires -Version 5.1
<#
.SYNOPSIS
Read-only: report which boot entry we are running, the pending bootsequence, and the test entry's
settings. Answers "did arm D actually take effect?" without changing anything.
#>
$ErrorActionPreference = 'Continue'
$stateFile = Join-Path $PSScriptRoot 'windows-ab\boot-ab-state.json'
$GUID_RE = '\{[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\}'

function Bcd([string]$cmdline) {
    $out = (& cmd.exe /c $cmdline 2>&1 | Out-String)
    [pscustomobject]@{ Exit = $LASTEXITCODE; Out = ($out -replace "`r", '').Trim() }
}
function Show([string]$title, [string]$cmd) {
    Write-Output "### $title"
    Write-Output "  \$ $cmd"
    $r = Bcd $cmd
    Write-Output "  exit=$($r.Exit)"
    foreach ($ln in ($r.Out -split "`n")) { Write-Output ("  " + $ln.TrimEnd()) }
    Write-Output ''
}

$os = Get-CimInstance Win32_OperatingSystem
Write-Output "LastBootUpTime = $($os.LastBootUpTime.ToString('o'))"
Write-Output "Now            = $((Get-Date).ToString('o'))"
Write-Output "Uptime         = $((Get-Date) - $os.LastBootUpTime)"
$hv = (Get-CimInstance Win32_ComputerSystem).HypervisorPresent
$dg = Get-CimInstance -Namespace 'root\Microsoft\Windows\DeviceGuard' -ClassName Win32_DeviceGuard
Write-Output "HypervisorPresent              = $hv"
Write-Output "VBS status (2=running)         = $($dg.VirtualizationBasedSecurityStatus)"
Write-Output "SecurityServicesRunning        = [$($dg.SecurityServicesRunning -join ',')]  (2=HVCI)"
Write-Output "SecurityServicesConfigured     = [$($dg.SecurityServicesConfigured -join ',')]  (2=HVCI, 3=SystemGuard)"
Write-Output "RequiredSecurityProperties     = [$($dg.RequiredSecurityProperties -join ',')]  (1=base virt, 2=secureboot, 3=DMA)"
Write-Output ''
Write-Output '=== arm state recorded by the script ==='
if (Test-Path $stateFile) { Get-Content $stateFile -Raw } else { Write-Output '(no state file)' }
Write-Output ''
Show 'which entry are we running now?' 'bcdedit /enum {current} /v'
Show 'boot manager (shows any pending bootsequence)' 'bcdedit /enum {bootmgr} /v'

$st = $null
if (Test-Path $stateFile) { try { $st = Get-Content $stateFile -Raw | ConvertFrom-Json } catch {} }
if ($st -and $st.TargetId) {
    Show "test entry $($st.TargetId) settings" "bcdedit /enum $($st.TargetId) /v"
    Write-Output 'INTERPRETATION:'
    Write-Output '  * if the {current} identifier above EQUALS the test entry id, we booted the test entry.'
    Write-Output '  * if it equals the OriginalId, the one-shot bootsequence was already consumed (or never fired).'
    Write-Output '  * if the test entry shows hypervisorlaunchtype Off and the hypervisor is still present,'
    Write-Output '    then VBS/common-criteria is forcing it and arm D is NOT reachable without disabling VBS.'
}
