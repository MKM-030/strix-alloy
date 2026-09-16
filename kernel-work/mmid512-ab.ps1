# mmid512-ab.ps1 - A/B the MMID_512 MoE routing fast path, WITHIN ONE BINARY.
#
# The guard is `getenv("GGML_CUDA_DISABLE_MMID_512") == nullptr`, so both arms run the SAME
# llama-server.exe and ggml-hip.dll: the only difference is one environment variable. That removes
# every build/link/stale-source confound that a DLL swap would introduce, so a small delta is
# trustworthy.
#
# Why this kernel could matter: for decode, n_tokens = 1, so the generic helper launches
# num_blocks = n_experts = 512 blocks, each with one warp, to place 10 expert slots. The 512_10 path
# does the same work in ONE 1024-thread block. That is 512x fewer block launches per Moe layer per
# token, on a graph that runs 48 layers.
#
# Correctness is checked, not assumed: both arms generate greedily with the same seed and the emitted
# text is compared. This kernel builds the expert->row maps, so a wrong map corrupts MoE output.
param(
    [int]$Ctx = 40960,
    [int]$Port = 8620,
    [int]$Gen = 128,
    [int]$Repeats = 3,
    [int]$Rounds = 2,
    [string]$Sizes = '8192,16384'
)
$ErrorActionPreference = 'Continue'
$bin   = 'C:\AI\build\strix-llama-win\build-therock\bin\llama-server.exe'
$sdk   = 'C:\AI\sdk\therock1151'
$model = 'C:\AI\models\qwen38-flash\projfix\Qwen3.8-Flash-Next-IQ4_NL-PROJFIX-00001-of-00009.gguf'
$res   = 'C:\Projects\strix-alloy\kernel-work\results'
$root  = 'C:\Projects\strix-alloy\kernel-work'

$env:PATH = "$sdk\bin;$sdk\lib\llvm\bin;$env:PATH"
$env:ROCM_PATH = $sdk; $env:HIP_PATH = $sdk
$env:HIP_DEVICE_LIB_PATH = "$sdk\lib\llvm\amdgcn\bitcode"
$env:HSA_OVERRIDE_GFX_VERSION = '11.5.1'

$PROMPT = 'Explain how a modern mixture-of-experts transformer routes a token to its top-k experts, how the expert outputs are combined, and why the routing overhead is proportionally larger at batch size one than during prefill. Give concrete numbers for a 512-expert model with top-10 routing.'

function Run-Arm([string]$arm, [int]$round) {
    Get-Process llama-server -ErrorAction SilentlyContinue | ForEach-Object { & taskkill /F /PID $_.Id 2>&1 | Out-Null }
    Start-Sleep -Seconds 5

    if ($arm -eq 'off') { $env:GGML_CUDA_DISABLE_MMID_512 = '1' } else { Remove-Item Env:\GGML_CUDA_DISABLE_MMID_512 -ErrorAction SilentlyContinue }

    $tag  = "mmid-$arm-r$round"
    $sout = Join-Path $res "$tag.out"; $serr = Join-Path $res "$tag.err"
    Remove-Item $sout, $serr -ErrorAction SilentlyContinue
    $a = @('-m', $model, '-dev', 'ROCm0', '-ngl', '99', '-fa', 'on', '-fit', 'off', '--load-mode', 'none',
           '-ctk', 'f16', '-ctv', 'f16', '-c', "$Ctx", '-b', '16384', '-ub', '16384',
           '--parallel', '1', '--host', '127.0.0.1', '--port', "$Port", '--no-webui', '--seed', '1234')
    $p = Start-Process -FilePath $bin -ArgumentList $a -PassThru -NoNewWindow `
                       -RedirectStandardOutput $sout -RedirectStandardError $serr
    $ok = $false; $t0 = Get-Date
    while (((Get-Date) - $t0).TotalSeconds -lt 600) {
        if ($p.HasExited) { break }
        try { if ((Invoke-WebRequest "http://127.0.0.1:$Port/health" -TimeoutSec 5 -UseBasicParsing).StatusCode -eq 200) { $ok = $true; break } } catch { Start-Sleep -Seconds 4 }
    }
    if (-not $ok) {
        Write-Output "[$tag] NOT READY"
        Select-String -Path $serr -Pattern 'failed to allocate|out of memory|error' | Select-Object -Last 2 | ForEach-Object { Write-Output ('   ' + $_.Line.Trim()) }
        if (-not $p.HasExited) { & taskkill /F /PID $p.Id 2>&1 | Out-Null }
        return $null
    }

    # --- perf: exact-size prompts via fnbench (no drafter, so the routing path is exercised plainly)
    $out = Join-Path $res "$tag.json"
    python "$root\fnbench.py" --port $Port --label $tag --sizes $Sizes --gen $Gen --repeats $Repeats `
        --context-limit ($Ctx - $Gen - 64) --out $out 2>&1 | Out-Null

    # --- correctness: greedy text at temp 0, same seed both arms; must be byte-identical
    $text = ''
    try {
        $body = @{ prompt = $PROMPT; n_predict = 64; cache_prompt = $false; temperature = 0.0;
                   top_k = 1; top_p = 1.0; min_p = 0.0; stream = $false; seed = 1234 } | ConvertTo-Json
        $r = Invoke-RestMethod -Uri "http://127.0.0.1:$Port/completion" -Method Post -Body $body `
             -ContentType 'application/json' -TimeoutSec 900
        $text = $r.content
        Set-Content -Path (Join-Path $res "$tag.txt") -Value $text -Encoding UTF8
    } catch { Write-Output "[$tag] correctness request failed: $_" }

    Get-Process llama-server -ErrorAction SilentlyContinue | ForEach-Object { & taskkill /F /PID $_.Id 2>&1 | Out-Null }
    Start-Sleep -Seconds 3

    if (-not (Test-Path $out)) { Write-Output "[$tag] no json"; return $null }
    $j = Get-Content $out -Raw | ConvertFrom-Json
    $rows = $j.rows | Where-Object { -not $_.error }
    $dec  = ($rows | ForEach-Object { $_.decode_tps })  | Sort-Object
    $pre  = ($rows | ForEach-Object { $_.prefill_tps }) | Sort-Object
    if ($dec.Count -eq 0) { Write-Output "[$tag] no valid rows"; return $null }
    Write-Output ("[{0}] decode median={1:N3} t/s  prefill median={2:N1} t/s  (n={3})  textlen={4}" -f `
        $tag, $dec[[int]($dec.Count/2)], $pre[[int]($pre.Count/2)], $dec.Count, $text.Length)
    return [pscustomobject]@{ arm = $arm; round = $round; decode = $dec[[int]($dec.Count/2)]; prefill = $pre[[int]($pre.Count/2)]; text = $text }
}

$all = @()
for ($r = 1; $r -le $Rounds; $r++) {
    # on = fast path active (env var unset); off = generic path
    $on  = Run-Arm 'on'  $r
    $off = Run-Arm 'off' $r
    if ($on)  { $all += $on }
    if ($off) { $all += $off }
}

Write-Output ''
Write-Output '=== aggregate (same binary, env-var toggle) ==='
foreach ($arm in 'on','off') {
    $v = ($all | Where-Object { $_.arm -eq $arm } | ForEach-Object { $_.decode }) | Sort-Object
    if ($v.Count -gt 0) {
        Write-Output ("  {0,-4} decode median={1:N3} t/s   rounds: {2}" -f $arm, $v[[int]($v.Count/2)], (($all | Where-Object { $_.arm -eq $arm } | ForEach-Object { '{0:N2}' -f $_.decode }) -join ', '))
    }
}
$onv  = ($all | Where-Object { $_.arm -eq 'on'  } | ForEach-Object { $_.decode }) | Sort-Object
$offv = ($all | Where-Object { $_.arm -eq 'off' } | ForEach-Object { $_.decode }) | Sort-Object
if ($onv.Count -gt 0 -and $offv.Count -gt 0) {
    $a1 = $onv[[int]($onv.Count/2)]; $b1 = $offv[[int]($offv.Count/2)]
    Write-Output ("  decode delta (on vs off) = {0:+0.00;-0.00} t/s ({1:+0.0;-0.0}%)" -f ($a1-$b1), (100*($a1-$b1)/$b1))
}
$pon  = ($all | Where-Object { $_.arm -eq 'on'  } | ForEach-Object { $_.prefill }) | Sort-Object
$poff = ($all | Where-Object { $_.arm -eq 'off' } | ForEach-Object { $_.prefill }) | Sort-Object
if ($pon.Count -gt 0 -and $poff.Count -gt 0) {
    $a2 = $pon[[int]($pon.Count/2)]; $b2 = $poff[[int]($poff.Count/2)]
    Write-Output ("  prefill delta (on vs off) = {0:+0.0;-0.0} t/s ({1:+0.0;-0.0}%)" -f ($a2-$b2), (100*($a2-$b2)/$b2))
}

Write-Output ''
Write-Output '=== correctness (greedy text must match exactly) ==='
$ontexts  = $all | Where-Object { $_.arm -eq 'on'  -and $_.text } | ForEach-Object { $_.text }
$offtexts = $all | Where-Object { $_.arm -eq 'off' -and $_.text } | ForEach-Object { $_.text }
if ($ontexts.Count -gt 0 -and $offtexts.Count -gt 0) {
    $distinct = ($ontexts + $offtexts) | Select-Object -Unique
    if ($distinct.Count -eq 1) {
        Write-Output "  MATCH - all $($ontexts.Count + $offtexts.Count) generations byte-identical ($($ontexts[0].Length) chars)"
    } else {
        Write-Output "  ** MISMATCH ** - $($distinct.Count) distinct outputs"
        $i = 0
        foreach ($d in $distinct) {
            $i++
            Write-Output ("   output $i : " + $d.Substring(0, [Math]::Min(220, $d.Length)).Replace("`n"," "))
        }
    }
} else { Write-Output '  no text captured' }
$all | Select-Object arm,round,decode,prefill | ConvertTo-Json -Depth 3 | Set-Content (Join-Path $res 'mmid512-ab.json')
Write-Output 'done'
