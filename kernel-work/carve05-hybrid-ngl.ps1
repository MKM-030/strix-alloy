# carve05-hybrid-ngl.ps1 - what does partial offload cost at a 0.5 GB carve?
#
# The user's hypothesis: this is unified LPDDR5X, so a layer resident in host RAM
# should be read at the same bandwidth as one resident in the device pool, and a
# 0.5 GB carve (127.5 GB host) should therefore be free. Test it: put fewer layers
# on the GPU with -ngl and measure decode throughput against the 96 GB baseline.
param(
    [int[]]$NglList = @(41, 36, 30, 24),
    [int]$Port = 8480,
    [string]$Results = 'C:\Projects\strix-alloy\kernel-work\results'
)
$ErrorActionPreference = 'Continue'
$bin   = 'C:\AI\build\strix-llama-win\build-therock\bin\llama-server.exe'
$sdk   = 'C:\AI\sdk\therock1151'
$model = 'C:\AI\models\qwen38-flash\projfix\Qwen3.8-Flash-Next-IQ4_NL-PROJFIX-00001-of-00009.gguf'
$draft = 'C:\AI\models\qwen38-flash\projfix\mtp-head-Qwen3.8-Flash-Next.gguf'

$env:PATH = "$sdk\bin;$sdk\lib\llvm\bin;$env:PATH"
$env:ROCM_PATH = $sdk; $env:HIP_PATH = $sdk
$env:HIP_DEVICE_LIB_PATH = "$sdk\lib\llvm\amdgcn\bitcode"
$env:HSA_OVERRIDE_GFX_VERSION = '11.5.1'
# NOTE: the build only honours GGML_CUDA_ENABLE_UNIFIED_MEMORY (ggml-cuda.cu:156);
# GGML_HIP_* is inert. Kept set only to match the probe; it changes nothing here.
$env:GGML_CUDA_ENABLE_UNIFIED_MEMORY = '1'

$rows = @()
foreach ($ngl in $NglList) {
    Write-Output "=================== -ngl $ngl ==================="
    Get-Process llama-server -EA SilentlyContinue | Stop-Process -Force
    Start-Sleep -Seconds 4
    $out = Join-Path $Results "hyb-ngl$ngl.out"
    $err = Join-Path $Results "hyb-ngl$ngl.err"
    Remove-Item $out, $err -EA SilentlyContinue

    $a = @('-m', $model, '-md', $draft, '-dev', 'ROCm0', '-ngl', "$ngl",
           '-fa', 'on', '-fit', 'off', '--load-mode', 'none',
           '-ctk', 'f16', '-ctv', 'f16', '-c', '16384', '-b', '2048', '-ub', '2048',
           '--parallel', '1', '--host', '127.0.0.1', '--port', "$Port", '--no-webui',
           '--seed', '1234', '--jinja', '--spec-type', 'draft-mtp',
           '--spec-draft-device', 'ROCm0', '--spec-draft-ngl', '99', '--spec-draft-n-max', '2')
    $p = Start-Process -FilePath $bin -ArgumentList $a -PassThru -NoNewWindow `
                       -RedirectStandardOutput $out -RedirectStandardError $err

    $ready = $false
    for ($i = 0; $i -lt 90; $i++) {
        Start-Sleep -Seconds 5
        if ($p.HasExited) { break }
        $m = Select-String -Path $err -Pattern 'listening on' -EA SilentlyContinue
        if ($m) { $ready = $true; break }
    }
    if (-not $ready) {
        Write-Output "  DID NOT LOAD (exit=$($p.HasExited))"
        Select-String -Path $err -Pattern 'failed to allocate|out of memory|error' -EA SilentlyContinue |
            Select-Object -First 4 | ForEach-Object { Write-Output ('  ' + $_.Line.Trim()) }
        $rows += [pscustomobject]@{ ngl = $ngl; loaded = $false; decode = $null; prefill = $null }
        continue
    }

    # how many layers actually went to the GPU, and the pool split
    Select-String -Path $err -Pattern 'offloaded|model buffer size|ROCm0 model' -EA SilentlyContinue |
        Select-Object -First 3 | ForEach-Object { Write-Output ('  ' + $_.Line.Trim()) }

    try {
        $body = @{ prompt = 'Explain the difference between gated linear attention and full attention in a mixture-of-experts transformer, then give a worked numeric example of the per-layer memory traffic for a batch of one.'; n_predict = 128; cache_prompt = $false; temperature = 0.0; top_k = 1; top_p = 1.0; min_p = 0.0; stream = $false } | ConvertTo-Json
        $r = Invoke-RestMethod -Uri "http://127.0.0.1:$Port/completion" -Method Post -Body $body -ContentType 'application/json' -TimeoutSec 900
        $t = $r.timings
        Write-Output ("  prefill={0:N1} t/s  decode={1:N2} t/s  acc={2}/{3}" -f $t.prompt_per_second, $t.predicted_per_second, $t.draft_n_accepted, $t.draft_n)
        $rows += [pscustomobject]@{ ngl = $ngl; loaded = $true; prefill = [math]::Round($t.prompt_per_second,1); decode = [math]::Round($t.predicted_per_second,2) }
    } catch {
        Write-Output "  request failed: $_"
        $rows += [pscustomobject]@{ ngl = $ngl; loaded = $true; decode = $null; prefill = $null }
    }
    if (-not $p.HasExited) { Stop-Process -Id $p.Id -Force }
    Start-Sleep -Seconds 2
}

Write-Output ''
Write-Output '=== SUMMARY (0.5 GB carve, MTP n-max 2, ub 2048) ==='
$rows | Format-Table -AutoSize | Out-String | Write-Output
$rows | ConvertTo-Json -Depth 4 | Set-Content (Join-Path $Results 'carve05-hybrid-ngl.json')
