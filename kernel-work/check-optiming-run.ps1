#requires -Version 5.1
# check-optiming-run.ps1 — did the op-timing instrumentation actually work, and did it destabilise?
foreach ($tag in @('nomtp','mtp')) {
    $p = "C:\Projects\REV-N-ornith-eval-20260911\kernel-work\results\opd-$tag.err"
    Write-Output "########## $tag ##########"
    if (-not (Test-Path $p)) { Write-Output '  missing'; continue }
    $t = [IO.File]::ReadAllText($p)
    $lines = ($t -replace "`r", '') -split "`n"

    $agg = ($lines | Where-Object { $_ -match 'OP_TIMING aggregate' }).Count
    $ig  = ($lines | Where-Object { $_ -match 'OP_TIMING_IG' }).Count
    Write-Output ("  headers: OP_TIMING aggregate={0}  OP_TIMING_IG={1}" -f $agg, $ig)

    $zero = ($lines | Where-Object { $_ -match 'OP_TIMING_IG.*tracked total 0\.0 ms/replay' }).Count
    Write-Output ("  IG zero-total lines: {0}" -f $zero)

    Write-Output '  --- errors / crashes ---'
    $errs = $lines | Where-Object { $_ -match 'failed|ROCm error|abort|assert|EXITED' }
    if ($errs) { foreach ($e in ($errs | Select-Object -First 8)) { Write-Output ("    " + $e.Trim()) } }
    else { Write-Output '    (none)' }

    Write-Output '  --- decode throughput achieved ---'
    $perf = $lines | Where-Object { $_ -match 'eval time|tg = |predicted' }
    foreach ($x in ($perf | Select-Object -Last 4)) { Write-Output ("    " + $x.Trim()) }

    Write-Output '  --- last 6 non-empty lines ---'
    foreach ($x in ($lines | Where-Object { $_.Trim() } | Select-Object -Last 6)) { Write-Output ("    " + $x.TrimEnd()) }
    Write-Output ''
}

Write-Output '=== race safety: is our earlier CPY/CONT number from the AGGREGATE path? ==='
Write-Output '  The aggregate path comment says it REQUIRES GGML_CUDA_DISABLE_GRAPHS=1.'
Write-Output '  If graphs were ON, those event pairs become graph nodes -> the numbers may be perturbed.'
