#requires -Version 5.1
# gpu-health.ps1 — is the ROCm device present/present-but-wedged, and which entry are we on?
# Read-only.
$ErrorActionPreference = 'Continue'
function Bcd([string]$c) {
    $o = (& cmd.exe /c $c 2>&1 | Out-String)
    [pscustomobject]@{ Exit = $LASTEXITCODE; Out = ($o -replace "`r", '').Trim() }
}

Write-Output '=== which boot entry is running ==='
$r = Bcd 'bcdedit /enum {current} /v'
foreach ($ln in ($r.Out -split "`n")) {
    if ($ln -match '^\s*(identifier|description|hypervisorlaunchtype|vsmlaunchtype|hypervisoriommupolicy)\s') {
        Write-Output ("  " + $ln.Trim())
    }
}

Write-Output ''
Write-Output '=== does the NORMAL (default) entry carry any leftover test setting? ==='
$d = Bcd 'bcdedit /enum {bootmgr} /v'
$def = $null
foreach ($ln in ($d.Out -split "`n")) {
    if ($ln -match '^\s*default\s+(\{[0-9a-fA-F-]+\})') { $def = $Matches[1] }
}
Write-Output "  default entry = $def"
if ($def) {
    $e = Bcd "bcdedit /enum $def /v"
    $found = $false
    foreach ($ln in ($e.Out -split "`n")) {
        if ($ln -match '^\s*(identifier|description|hypervisorlaunchtype|vsmlaunchtype|hypervisoriommupolicy)\s') {
            Write-Output ("  " + $ln.Trim()); $found = $true
        }
    }
    if (-not $found) { Write-Output '  (no relevant settings present -> clean)' }
}

Write-Output ''
Write-Output '=== GPU devices (PnP) ==='
$gpus = Get-PnpDevice -PresentOnly -ErrorAction SilentlyContinue |
    Where-Object { $_.Class -in @('Display','ComputeAccelerator') -or $_.FriendlyName -match 'Radeon|8060|NPU' }
foreach ($g in $gpus) {
    Write-Output ("  [{0}] {1}  problem={2}  instance={3}" -f $g.Status, $g.FriendlyName, $g.Problem, $g.InstanceId)
}

Write-Output ''
Write-Output '=== any device with a problem code right now? ==='
$bad = Get-PnpDevice -PresentOnly -ErrorAction SilentlyContinue |
    Where-Object { $_.Status -ne 'OK' -and $_.Problem -ne 'CM_PROB_NONE' }
if ($bad) { foreach ($b in $bad) { Write-Output ("  [{0}] {1} problem={2}" -f $b.Status, $b.FriendlyName, $b.Problem) } }
else { Write-Output '  none' }

Write-Output ''
Write-Output '=== recent display-driver errors in the System log (last 30 min) ==='
$since = (Get-Date).AddMinutes(-30)
try {
    Get-WinEvent -FilterHashtable @{ LogName='System'; StartTime=$since; Level=@(1,2,3) } -MaxEvents 20 -ErrorAction Stop |
        Where-Object { $_.ProviderName -match 'Display|amdkmpfd|amdkmdag|nvlddmkm|dxgkrnl|WHEA' } |
        ForEach-Object { Write-Output ("  {0} [{1}] {2}" -f $_.TimeCreated.ToString('HH:mm:ss'), $_.ProviderName, ($_.Message -split "`n")[0]) }
    if (-not $?) { Write-Output '  (query returned nothing)' }
} catch { Write-Output "  log query failed: $($_.Exception.Message)" }

Write-Output ''
Write-Output '=== is the AMD kernel driver running? ==='
$svc = Get-Service -Name 'amdkmpfd','amdkmdag' -ErrorAction SilentlyContinue
if ($svc) { foreach ($s in $svc) { Write-Output ("  {0}: Status={1} StartType={2}" -f $s.Name, $s.Status, $s.StartType) } }
else { Write-Output '  (driver services not found by that name)' }
