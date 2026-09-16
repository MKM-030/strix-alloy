#requires -Version 5.1
<#
.SYNOPSIS
Prepares and manages reversible Windows boot states for a Strix Halo inference A/B.
.DESCRIPTION
Two methods, because this machine's BCD store reports its loader identifier as the literal virtual id
{current} (probe with .\bcd-probe.ps1 first):

  -Method Copy          (preferred) bcdedit /copy <loader> /d "<desc>", change only the copy, arm the copy
                        for the NEXT BOOT ONLY. The original entry is never modified.
  -Method DirectToggle  (fallback) change hypervisorlaunchtype on the RUNNING entry, remembering the old
                        value, and restore it afterwards. Simpler, but see the RISK note below.

Neither method touches firmware IOMMU, SVM, Secure Boot, the carve, drivers or power settings.
This script NEVER reboots.

RISK (DirectToggle): the running entry is edited. If the machine could not boot with the new setting you
would need WinRE to restore it. `hypervisorlaunchtype off` is a supported, non-boot-critical setting, so
this is unlikely -- but it is the reason Copy is preferred.

Arms: D = no hypervisor | B = no VSM | C = B + no hypervisor IOMMU policy
.EXAMPLE
  .\windows-boot-ab.ps1 -Diagnose
  .\windows-boot-ab.ps1 -Status
  .\windows-boot-ab.ps1 -Arm D -ConfirmArm
  .\windows-boot-ab.ps1 -Arm D -Method DirectToggle -ConfirmArm
  .\windows-boot-ab.ps1 -Restore
#>
[CmdletBinding(DefaultParameterSetName='Status')]
param(
    [Parameter(ParameterSetName='Arm', Mandatory=$true)]
    [ValidateSet('D','B','C')][string]$Arm,
    [Parameter(ParameterSetName='Arm')]
    [ValidateSet('Copy','DirectToggle')][string]$Method = 'Copy',
    [Parameter(ParameterSetName='Restore', Mandatory=$true)][switch]$Restore,
    [Parameter(ParameterSetName='RemoveAll', Mandatory=$true)][switch]$RemoveAll,
    [Parameter(ParameterSetName='Status', Mandatory=$true)][switch]$Status,
    [Parameter(ParameterSetName='Diagnose', Mandatory=$true)][switch]$Diagnose,
    [string]$WorkRoot,
    [switch]$ConfirmArm
)
$ErrorActionPreference = 'Stop'
if ($env:OS -ne 'Windows_NT') { throw 'Windows only.' }
if (-not $WorkRoot -or $WorkRoot.Trim() -eq '') { $WorkRoot = Join-Path $PSScriptRoot 'windows-ab' }
New-Item -ItemType Directory -Path $WorkRoot -Force | Out-Null
$stateFile = Join-Path $WorkRoot 'boot-ab-state.json'
$GUID_RE = '\{[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\}'

function Is-Admin {
    $id = [Security.Principal.WindowsIdentity]::GetCurrent()
    (New-Object Security.Principal.WindowsPrincipal($id)).IsInRole(
        [Security.Principal.WindowsBuiltInRole]::Administrator)
}
function Bcd([string]$cmdline) {
    $out = (& cmd.exe /c $cmdline 2>&1 | Out-String)
    [pscustomobject]@{ Cmd = $cmdline; Exit = $LASTEXITCODE; Out = ($out -replace "`r", '').Trim() }
}
function GuidsOf([string]$text) {
    @([regex]::Matches($text, $GUID_RE) | ForEach-Object { $_.Value } | Sort-Object -Unique)
}
# candidates to address the running Windows boot loader: concrete GUIDs if present, else {current}
function Get-LoaderCandidates {
    $c = New-Object System.Collections.ArrayList
    $r = Bcd 'bcdedit /enum all /v'
    if ($r.Exit -eq 0) {
        $inLoader = $false
        foreach ($ln in ($r.Out -split "`n")) {
            if ($ln -match '^\s*Windows Boot Loader\s*$') { $inLoader = $true; continue }
            if ($inLoader -and $ln -match '^\s*identifier\s+(\S+)') {
                $id = $Matches[1]
                if ($id -notmatch $GUID_RE) { $inLoader = $false; continue }
                if (-not $c.Contains($id)) { [void]$c.Add($id) }
                $inLoader = $false
            }
            if ($inLoader -and $ln -match '^\s*(Windows Boot Manager|Device options|Firmware Application)') { $inLoader = $false }
        }
    }
    if (-not $c.Contains('{current}')) { [void]$c.Add('{current}') }
    return @($c)
}
function Read-HypervisorType([string]$id) {
    $t = if ($id -eq '{current}' -or -not $id) { Bcd 'bcdedit /enum ACTIVE /v' } else { Bcd "bcdedit /enum $id /v" }
    foreach ($ln in ($t.Out -split "`n")) {
        if ($ln -match '^\s*hypervisorlaunchtype\s+(\S+)') { return $Matches[1] }
    }
    return $null
}
# Concrete GUID of the normal/default boot entry, for -Restore. Only accepts a real GUID: this
# store sometimes reports the literal virtual id {current}, and bootsequence {current} would be
# WRONG after booting into the test entry (it would mean the test entry itself).
function Get-DefaultEntryId {
    foreach ($spec in @('{bootmgr}','ACTIVE')) {
        $r = Bcd "bcdedit /enum $spec /v"
        if ($r.Exit -ne 0) { continue }
        foreach ($ln in ($r.Out -split "`n")) {
            if ($ln -match ('^\s*default\s+(' + $GUID_RE + ')')) { return $Matches[1] }
        }
    }
    return $null
}
function Read-State {
    $s = @{ Method = $null; OriginalId = $null; TargetId = $null; PrevHypervisor = $null
            TestIds = @(); LastArm = $null; ArmedAt = $null }
    if (Test-Path $stateFile) {
        try {
            $j = Get-Content $stateFile -Raw | ConvertFrom-Json
            foreach ($k in @('Method','OriginalId','TargetId','PrevHypervisor','LastArm','ArmedAt')) {
                if ($j.PSObject.Properties[$k] -and $j.$k) { $s[$k] = [string]$j.$k }
            }
            if ($j.TestIds) { $s.TestIds = @($j.TestIds) }
        } catch { Write-Warning "state file unreadable, starting fresh: $($_.Exception.Message)" }
    }
    return $s
}
function Write-State($s) { $s | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $stateFile -Encoding UTF8 }

function Show-State {
    $hv = (Get-CimInstance Win32_ComputerSystem).HypervisorPresent
    $dg = Get-CimInstance -Namespace 'root\Microsoft\Windows\DeviceGuard' -ClassName Win32_DeviceGuard
    Write-Output "HypervisorPresent              = $hv"
    Write-Output "VBS status (2=running)         = $($dg.VirtualizationBasedSecurityStatus)"
    Write-Output "SecurityServicesRunning        = [$($dg.SecurityServicesRunning -join ',')]  (2=HVCI)"
    Write-Output "RequiredSecurityProperties     = [$($dg.RequiredSecurityProperties -join ',')]  (3=DMA protection)"
    $dgk = Get-ItemProperty 'HKLM:\SYSTEM\CurrentControlSet\Control\DeviceGuard' -ErrorAction SilentlyContinue
    if ($null -ne $dgk) { Write-Output "DeviceGuard Locked              = $($dgk.Locked)  (0 = not UEFI-locked)" }
    $lsa = Get-ItemProperty 'HKLM:\SYSTEM\CurrentControlSet\Control\Lsa' -ErrorAction SilentlyContinue
    if ($null -ne $lsa) { Write-Output "Credential Guard (LsaCfgFlags) = $($lsa.LsaCfgFlags)" }
    Write-Output "Elevated                       = $(Is-Admin)"
    Write-Output "hypervisorlaunchtype (running) = $(Read-HypervisorType '{current}')"
}

# ------------------------------------------------------------------ Diagnose
if ($PSCmdlet.ParameterSetName -eq 'Diagnose') {
    Show-State
    Write-Output ''
    Write-Output "loader id candidates = $((Get-LoaderCandidates) -join ', ')"
    $def = Get-DefaultEntryId
    Write-Output "default (restore target) GUID = $(if ($def) { $def } else { '<not concrete>' })"
    Write-Output ''
    Write-Output '### bcdedit /enum ACTIVE /v ###'
    $r = Bcd 'bcdedit /enum ACTIVE /v'
    Write-Output "exit=$($r.Exit)"; Write-Output $r.Out
    Write-Output ''
    Write-Output 'For a safe end-to-end check of arming, run:  .\bcd-probe.ps1'
    return
}

# ------------------------------------------------------------------ Status
if ($PSCmdlet.ParameterSetName -eq 'Status') {
    Show-State
    Write-Output ''
    $s = Read-State
    Write-Output "state file: $stateFile"
    Write-Output "  Method=$($s.Method)  LastArm=$($s.LastArm)  ArmedAt=$($s.ArmedAt)"
    Write-Output "  OriginalId=$($s.OriginalId)  TargetId=$($s.TargetId)  PrevHypervisor=$($s.PrevHypervisor)"
    Write-Output "  TestIds=$($s.TestIds -join ', ')"
    Write-Output ''
    Write-Output "loader id candidates = $((Get-LoaderCandidates) -join ', ')"
    return
}

# ------------------------------------------------------------------ mutations need elevation
if (-not (Is-Admin)) {
    if ($PSCmdlet.ParameterSetName -eq 'Arm' -and -not $ConfirmArm) {
        Write-Output '=== pre-flight (non-elevated preview) ==='
        Show-State
        Write-Output ''
        Write-Output "Arm $Arm with -Method $Method would:"
        if ($Method -eq 'Copy') {
            Write-Output '  1. bcdedit /copy <loader> /d "<description>"   (original untouched)'
            Write-Output '  2. set the new entry: hypervisorlaunchtype/vsmlaunchtype (and iommu policy for C)'
            Write-Output '  3. bcdedit /bootsequence <new>   (NEXT BOOT ONLY)'
        } else {
            Write-Output '  1. edit the RUNNING entry''s hypervisorlaunchtype (previous value saved for restore)'
            Write-Output '  2. reboot normally; .\windows-boot-ab.ps1 -Restore puts it back'
        }
        Write-Output ''
        Write-Output 'Nothing has been changed by this preview. Re-run ELEVATED with -ConfirmArm.'
        return
    }
    throw 'Run this in an ELEVATED PowerShell. Nothing has been changed.'
}

$state = Read-State
$loader = @(Get-LoaderCandidates)
Write-Output "Elevated. loader id candidates: $($loader -join ', ')"

if ($Restore) {
    if ($state.Method -eq 'DirectToggle' -and $state.PrevHypervisor) {
        $tid = if ($state.TargetId) { $state.TargetId } else { '{current}' }
        $r = Bcd "bcdedit /set $tid hypervisorlaunchtype $($state.PrevHypervisor)"
        Write-Output "restore: set $tid hypervisorlaunchtype $($state.PrevHypervisor) -> exit=$($r.Exit) $($r.Out)"
        Write-Output "now reads: $(Read-HypervisorType $tid)"
    } elseif ($state.OriginalId -and ($state.OriginalId -match $GUID_RE)) {
        $r = Bcd "bcdedit /bootsequence $($state.OriginalId)"
        Write-Output "next boot restored to original entry $($state.OriginalId) -> exit=$($r.Exit) $($r.Out)"
    } else {
        # Only reachable for the Copy method when the store did not expose a concrete default GUID.
        # bootsequence is one-shot, so the normal entry already resumes on the boot after the test.
        Write-Output 'Nothing to restore: bootsequence is one-shot, so your normal entry resumes on the next boot.'
        if ($state.OriginalId) { Write-Output "  (recorded id was '$($state.OriginalId)', a virtual id -- not usable for bootsequence)" }
        $cur = Read-HypervisorType '{current}'
        Write-Output "  current hypervisorlaunchtype = $cur (should be Auto if you are already back on the normal entry)"
    }
    return
}

if ($RemoveAll) {
    foreach ($id in @($state.TestIds)) {
        if ($id) { $r = Bcd "bcdedit /delete $id /f"; Write-Output "$id -> exit=$($r.Exit) $($r.Out)" }
    }
    $state.TestIds = @(); $state.LastArm = $null; $state.ArmedAt = $null
    Write-State $state
    Write-Output 'Test entries deleted. Original entry untouched.'
    return
}

# ------------------------------------------------------------------ Arm
Write-Output ''
Write-Output '=== pre-flight ==='
Show-State
Write-Output ''
Write-Output 'Confirm: local console; BitLocker key if protection is ON (yours reported Off);'
Write-Output '         DeviceGuard Locked = 0; WSL2 unavailable on arm D; entries share registry/policy.'
Write-Output ''

if (-not $ConfirmArm) {
    Write-Output "DRY RUN. Nothing changed. Re-run with:  -Arm $Arm -Method $Method -ConfirmArm"
    return
}

$export = Join-Path $WorkRoot ('bcd-backup-' + (Get-Date -Format 'yyyyMMdd-HHmmss'))
$re = Bcd "bcdedit /export `"$export`""
Write-Output "BCD export -> exit=$($re.Exit) $($re.Out)  ($export)"

$desc = switch ($Arm) {
    'D' { 'Strix bench - no hypervisor' }
    'B' { 'Strix bench - no VSM' }
    'C' { 'Strix bench - no VSM + no hv IOMMU policy' }
}
$settings = switch ($Arm) {
    'D' { @(@('hypervisorlaunchtype','off'), @('vsmlaunchtype','off')) }
    'B' { @(@('hypervisorlaunchtype','auto'), @('vsmlaunchtype','off')) }
    'C' { @(@('hypervisorlaunchtype','auto'), @('vsmlaunchtype','off'), @('hypervisoriommupolicy','disable')) }
}

if ($Method -eq 'Copy') {
    # Copy source preference: the RECORDED ORIGINAL entry first, because when we are currently
    # booted into a previous test entry, {current} is that test entry and would inherit its
    # settings. Falling back to {current} is fine on a normal boot.
    $copyOut = $null; $newId = $null; $usedSrc = $null
    $srcCandidates = @()
    if ($state.OriginalId -and ($state.OriginalId -match $GUID_RE)) { $srcCandidates += $state.OriginalId }
    $srcCandidates += @('{current}') + $loader
    $srcCandidates = @($srcCandidates | Select-Object -Unique)
    Write-Output "copy-source candidates (preferred first): $($srcCandidates -join ', ')"
    foreach ($src in $srcCandidates) {
        $c = Bcd "bcdedit /copy $src /d `"$desc`""
        Write-Output "copy from $src -> exit=$($c.Exit) $($c.Out)"
        if ($c.Exit -eq 0) {
            $g = ([regex]::Match($c.Out, $GUID_RE)).Value
            if ($g) { $copyOut = $c.Out; $newId = $g; $usedSrc = $src; break }
        }
    }
    if (-not $newId) { throw "No /copy source worked. Use -Method DirectToggle. Nothing armed." }
    Write-Output "created $newId (from $usedSrc)"

    $okAll = $true
    foreach ($kv in $settings) {
        $rs = Bcd "bcdedit /set $newId $($kv[0]) $($kv[1])"
        Write-Output ("  set {0} = {1}  -> exit={2}" -f $kv[0], $kv[1], $rs.Exit)
        if ($rs.Exit -ne 0) { $okAll = $false; Write-Warning "    ^ FAILED: $($rs.Out)" }
    }
    $rb = Bcd "bcdedit /bootsequence $newId"
    Write-Output "bootsequence $newId -> exit=$($rb.Exit)"

    # read back what we actually armed (settings can be rejected individually)
    Write-Output '--- read-back of the armed entry ---'
    $chk = Bcd "bcdedit /enum $newId /v"
    foreach ($ln in ($chk.Out -split "`n")) {
        if ($ln -match '^\s*(hypervisorlaunchtype|vsmlaunchtype|hypervisoriommupolicy)\s') {
            Write-Output ("  " + $ln.Trim())
        }
    }

    $state.Method = 'Copy'; $state.OriginalId = (Get-DefaultEntryId); $state.TargetId = $newId
    $state.TestIds = @($state.TestIds) + $newId; $state.LastArm = $Arm; $state.ArmedAt = (Get-Date).ToString('o')
    Write-State $state
    Write-Output "original (default) GUID recorded = $(if ($state.OriginalId) { $state.OriginalId } else { '<not concrete; bootsequence is one-shot so this is fine>' })"

    Write-Output ''
    if ($okAll -and $rb.Exit -eq 0) {
        Write-Output "ARMED: the NEXT boot uses $newId ; the boot after returns to normal automatically."
        Write-Output 'REBOOT WHEN READY.'
    } else {
        Write-Warning 'ARM INCOMPLETE - do NOT reboot. Paste this output.'
    }
} else {
    # DirectToggle: edit the running entry, remember the previous value
    $hvTarget = if ($Arm -eq 'D') { 'off' } else { 'auto' }
    $prev = Read-HypervisorType '{current}'
    Write-Output "current hypervisorlaunchtype = $prev ; target = $hvTarget"
    $target = $null; $setOk = $false
    foreach ($cand in $loader) {
        $rs = Bcd "bcdedit /set $cand hypervisorlaunchtype $hvTarget"
        Write-Output "  set $cand hypervisorlaunchtype $hvTarget -> exit=$($rs.Exit) $($rs.Out)"
        if ($rs.Exit -eq 0) { $target = $cand; $setOk = $true; break }
    }
    if (-not $setOk) { throw "Could not set hypervisorlaunchtype on any candidate. Nothing changed." }
    foreach ($kv in @(@('vsmlaunchtype','off'))) {
        $rs = Bcd "bcdedit /set $target $($kv[0]) $($kv[1])"
        Write-Output ("  set {0} = {1}  -> exit={2}" -f $kv[0], $kv[1], $rs.Exit)
    }
    if ($Arm -eq 'C') {
        $rs = Bcd "bcdedit /set $target hypervisoriommupolicy disable"
        Write-Output "  set hypervisoriommupolicy = disable -> exit=$($rs.Exit)"
    }
    $state.Method = 'DirectToggle'; $state.TargetId = $target
    $state.PrevHypervisor = $prev; $state.LastArm = $Arm; $state.ArmedAt = (Get-Date).ToString('o')
    Write-State $state
    Write-Output ''
    Write-Output "ARMED (DirectToggle on $target): hypervisorlaunchtype was '$prev'."
    Write-Output 'REBOOT WHEN READY, then:  .\windows-boot-ab.ps1 -Restore'
    Write-Warning 'This edited the RUNNING entry. Restore before doing anything else after the test.'
}
