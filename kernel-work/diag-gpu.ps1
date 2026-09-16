#requires -Version 5.1
<#
.SYNOPSIS
READ-ONLY diagnosis: why can't ROCm see the GPU after the boot experiments?
.DESCRIPTION
Prints the WHOLE boot store (so there is nothing to guess at), plus Fast Startup and device state.
Changes NOTHING. Run elevated and paste the output.
#>
$ErrorActionPreference = 'Continue'
$res = Join-Path $PSScriptRoot 'results'
New-Item -ItemType Directory -Path $res -Force | Out-Null

function Is-Admin {
    $id = [Security.Principal.WindowsIdentity]::GetCurrent()
    (New-Object Security.Principal.WindowsPrincipal($id)).IsInRole(
        [Security.Principal.WindowsBuiltInRole]::Administrator)
}
function ReadTxt($p) {
    if (-not (Test-Path $p)) { return '' }
    $b = [IO.File]::ReadAllBytes($p)
    if ($b.Length -gt 4 -and $b[1] -eq 0) { return [Text.Encoding]::Unicode.GetString($b) }
    return [Text.Encoding]::UTF8.GetString($b)
}
function Bcd([string]$a, [string]$file) {
    $p = Join-Path $res $file
    # no -> file redirection: capture stdout+stderr through PowerShell, then write it ourselves
    $o = (& cmd.exe /c "bcdedit $a" 2>&1 | Out-String)
    $code = $LASTEXITCODE
    ($o -replace "`r", '') | Set-Content -LiteralPath $p -Encoding UTF8
    return @{ Path = $p; Code = $code; Text = ($o -replace "`r", '').Trim() }
}

Write-Output "Elevated = $(Is-Admin)"
Write-Output "Time     = $(Get-Date -Format o)"
$os = Get-CimInstance Win32_OperatingSystem
Write-Output "Booted   = $($os.LastBootUpTime.ToString('o'))   (uptime $((Get-Date) - $os.LastBootUpTime))"
$hv = (Get-CimInstance Win32_ComputerSystem).HypervisorPresent
$dg = Get-CimInstance -Namespace 'root\Microsoft\Windows\DeviceGuard' -ClassName Win32_DeviceGuard
Write-Output "HypervisorPresent = $hv ; VBS = $($dg.VirtualizationBasedSecurityStatus) ; Services = [$($dg.SecurityServicesRunning -join ',')]"

Write-Output ''
Write-Output '################ FULL BOOT STORE (bcdedit /enum all /v) ################'
$r = Bcd '/enum all /v' 'diag-all.txt'
Write-Output "exit=$($r.Code)"
Write-Output $r.Text

Write-Output ''
Write-Output '################ SCAN: hypervisor / iommu / vsm anywhere ################'
$found = $false
foreach ($ln in ($r.Text -split "`n")) {
    if ($ln -match '(?i)hypervisor|iommu|vsmlaunchtype|bootsequence') {
        Write-Output ("  " + $ln.Trim()); $found = $true
    }
}
if (-not $found) { Write-Output '  (nothing found)' }

Write-Output ''
Write-Output '################ GLOBAL CONTAINER: {hypervisorsettings} ################'
$rh = Bcd '/enum {hypervisorsettings} /v' 'diag-hvsettings.txt'
Write-Output ("exit={0} : {1}" -f $rh.Code, ($rh.Text -replace "`n", ' | '))

Write-Output ''
Write-Output '################ Fast Startup (1 = hybrid shutdown can carry driver state) ################'
$pw = Get-ItemProperty 'HKLM:\SYSTEM\CurrentControlSet\Control\Session Manager\Power' -ErrorAction SilentlyContinue
if ($pw -and $null -ne $pw.HiberbootEnabled) { Write-Output "  HiberbootEnabled = $($pw.HiberbootEnabled)" }
else { Write-Output '  HiberbootEnabled = <not present>' }

Write-Output ''
Write-Output '################ Devices ################'
foreach ($g in (Get-PnpDevice -PresentOnly -ErrorAction SilentlyContinue |
                Where-Object { $_.InstanceId -match 'VEN_1002&DEV_1586' -or $_.FriendlyName -match 'NPU Compute' })) {
    Write-Output ("  [{0}] {1}  problem={2}" -f $g.Status, $g.FriendlyName, $g.Problem)
}

Write-Output ''
Write-Output '################ Last 15 System errors (any provider) ################'
try {
    Get-WinEvent -FilterHashtable @{ LogName='System'; Level=@(1,2) } -MaxEvents 15 -ErrorAction Stop |
        ForEach-Object { Write-Output ("  {0} [{1}] {2}" -f $_.TimeCreated.ToString('HH:mm:ss'), $_.ProviderName, (($_.Message -split "`n")[0]).Trim()) }
} catch { Write-Output "  (none / query failed: $($_.Exception.Message))" }

Write-Output ''
Write-Output 'Paste this whole output.'
