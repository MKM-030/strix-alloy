#requires -Version 5.1
# parse-optiming.ps1 — pull the op-timing summary out of the server log and rank it.
param([string]$Log = 'C:\Projects\REV-N-ornith-eval-20260911\kernel-work\results\opb.err')
$t = [IO.File]::ReadAllText($Log)
$lines = ($t -replace "`r", '') -split "`n"

Write-Output '=== header / summary lines ==='
$hdr = $lines | Where-Object { $_ -match 'OP_TIMING|replays|per-op|=== ' }
if ($hdr) { foreach ($h in ($hdr | Select-Object -First 20)) { Write-Output ("  " + $h.TrimEnd()) } }
else { Write-Output '  (none found - output may be the graphs-off variant)' }

# collect the last summary block (most representative)
$blocks = @()
$cur = @()
foreach ($l in $lines) {
    if ($l -match '^\s*\S+\|\S*\s+n=\d+\s+total=') { $cur += $l }
    elseif ($cur.Count -gt 0) { $blocks += ,$cur; $cur = @() }
}
if ($cur.Count -gt 0) { $blocks += ,$cur }
Write-Output ''
Write-Output ("=== summary blocks found: {0} ===" -f $blocks.Count)

$use = if ($blocks.Count -ge 2) { $blocks[-1] } else { $blocks[0] }
if (-not $use) { Write-Output 'no op rows parsed'; return }

$rows = @()
foreach ($l in $use) {
    if ($l -match '^\s*(\S+)\|(\S*)\s+n=(\d+)\s+total=\s*([\d.]+)ms\s+avg=\s*([\d.]+)us') {
        $rows += [pscustomobject]@{
            op  = "$($Matches[1])|$($Matches[2])"
            n   = [int]$Matches[3]
            ms  = [double]$Matches[4]
            us  = [double]$Matches[5]
        }
    }
}
$tot = ($rows | Measure-Object ms -Sum).Sum
Write-Output ''
Write-Output ("=== tracked total: {0:N1} ms over {1} op-type rows ===" -f $tot, $rows.Count)
Write-Output ''
Write-Output '=== top 20 by total ms (share of tracked) ==='
$rows | Sort-Object ms -Descending | Select-Object -First 20 | ForEach-Object {
    $pct = if ($tot -gt 0) { 100.0 * $_.ms / $tot } else { 0 }
    Write-Output ("  {0,-26} n={1,-7} {2,9:N2} ms  {3,5:N1}%  avg={4,8:N1} us" -f $_.op, $_.n, $_.ms, $pct, $_.us)
}
Write-Output ''
Write-Output '=== grouped by op name (all layers merged) ==='
$rows | Group-Object { ($_.op -split '\|')[0] } | ForEach-Object {
    [pscustomobject]@{
        op = $_.Name
        ms = ($_.Group | Measure-Object ms -Sum).Sum
        n  = ($_.Group | Measure-Object n -Sum).Sum
    }
} | Sort-Object ms -Descending | Select-Object -First 20 | ForEach-Object {
    $pct = if ($tot -gt 0) { 100.0 * $_.ms / $tot } else { 0 }
    Write-Output ("  {0,-26} n={1,-7} {2,9:N2} ms  {3,5:N1}%" -f $_.op, $_.n, $_.ms, $pct)
}
