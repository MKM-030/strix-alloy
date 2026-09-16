#requires -Version 5.1
<#
.SYNOPSIS
Read-only + net-zero probe of this machine's BCD store, to find an arming path that actually works.
.DESCRIPTION
This system's boot loader entry reports its identifier as the literal virtual id {current}, which is why
GUID resolution failed. This probe tests, in order, which bcdedit operations succeed here.

NET EFFECT ON THE MACHINE: none. The copy it makes (if any) is deleted again before returning, and it
prints the before/after entry lists as proof. It does NOT change hypervisorlaunchtype, does not set a
bootsequence, and does not reboot.
#>
param([string]$WorkRoot)
$ErrorActionPreference = 'Continue'
if (-not $WorkRoot -or $WorkRoot.Trim() -eq '') { $WorkRoot = Join-Path $PSScriptRoot 'windows-ab' }
New-Item -ItemType Directory -Path $WorkRoot -Force | Out-Null
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

Write-Output "Elevated = $(Is-Admin)"
if (-not (Is-Admin)) { throw 'Run this in an ELEVATED PowerShell.' }

$r = Bcd 'bcdedit /enum all'
$before = GuidsOf $r.Out
Write-Output "distinct GUIDs in store before = $($before.Count)"
Write-Output ''
Write-Output '### which /enum specifiers parse here (elevated) ###'
foreach ($spec in @('{current}','{default}','{bootmgr}','ACTIVE','all')) {
    $t = Bcd "bcdedit /enum $spec"
    $verdict = if ($t.Exit -eq 0) { 'WORKS' } elseif ($t.Out -match 'invalid') { 'REJECTED (invalid entry type)' } else { "exit=$($t.Exit)" }
    Write-Output ("  /enum {0,-10} -> {1}" -f $spec, $verdict)
}

Write-Output ''
Write-Output '### identifier lines of the active loader (what bcdedit reports) ###'
$a = Bcd 'bcdedit /enum ACTIVE /v'
($a.Out -split "`n") | Where-Object { $_ -match '^\s*(identifier|default|displayorder|description)\s' } |
    ForEach-Object { Write-Output ("  " + $_.Trim()) }

Write-Output ''
Write-Output '### TEST: copy then delete via {current} (net-zero) ###'
$c = Bcd 'bcdedit /copy {current} /d "REVN probe - do not keep"'
Write-Output "  cmd : $($c.Cmd)"
Write-Output "  exit: $($c.Exit)"
Write-Output "  out : $($c.Out)"
$new = ([regex]::Match($c.Out, $GUID_RE)).Value
if ($new) {
    Write-Output "  -> created $new ; deleting it now"
    $d = Bcd "bcdedit /delete $new /f"
    Write-Output "  delete exit=$($d.Exit) out=$($d.Out)"
    $verify = GuidsOf (Bcd 'bcdedit /enum all').Out
    if ($verify -contains $new) { Write-Warning "  !! $new STILL PRESENT - clean it manually: bcdedit /delete $new /f" }
    else { Write-Output "  -> $new confirmed gone" }
    Write-Output ''
    Write-Output 'RECOMMENDATION: arming via /copy {current} WORKS. Safe to run:'
    Write-Output '   .\windows-boot-ab.ps1 -Arm D -ConfirmArm'
} else {
    Write-Output '  -> copy did not yield a GUID.'
    # did it create something we did not parse? compare lists
    $after = GuidsOf (Bcd 'bcdedit /enum all').Out
    $created = @($after | Where-Object { $before -notcontains $_ })
    if ($created.Count -gt 0) {
        Write-Warning "  created-but-unparsed entries: $($created -join ', ') -- deleting them"
        foreach ($g in $created) { Write-Output "    $g -> $((Bcd "bcdedit /delete $g /f").Out)" }
    } else {
        Write-Output '  no new entries appeared, so nothing to clean up.'
    }
    Write-Output ''
    Write-Output 'RECOMMENDATION: /copy {current} does not work here. Use the direct-toggle fallback instead:'
    Write-Output '   .\windows-boot-ab.ps1 -Arm D -Method DirectToggle -ConfirmArm'
}

$after2 = GuidsOf (Bcd 'bcdedit /enum all').Out
Write-Output ''
Write-Output "distinct GUIDs after = $($after2.Count)  (before was $($before.Count))"
Write-Output "state file written? $(Test-Path (Join-Path $WorkRoot 'boot-ab-state.json'))"
Write-Output 'Probe complete. No lasting change was made.'
