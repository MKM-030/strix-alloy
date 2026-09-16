# carve16-fit-tests.ps1 - find a config that runs at the CURRENT carve (~16 GB).
#
# At this carve the weights (66.01 GiB) now allocate; the compute buffer is what fails
# (5.94 GiB at -ub 16384), leaving a shortfall of roughly 1-2 GiB. The compute buffer
# scales with the ubatch, so a smaller -ub should fit. Each arm that loads is benchmarked
# so we know what the smaller batch costs.
param([int]$Port = 8540)
$ErrorActionPreference = 'Continue'
$bin   = 'C:\AI\build\strix-llama-win\build-therock\bin\llama-server.exe'
$sdk   = 'C:\AI\sdk\therock1151'
$model = 'C:\AI\models\qwen38-flash\projfix\Qwen3.8-Flash-Next-IQ4_NL-PROJFIX-00001-of-00009.gguf'
$draft = 'C:\AI\models\qwen38-flash\projfix\mtp-Qwen3.8-Flash-Next-shared-Q8_0.gguf'
$res   = 'C:\Projects\strix-alloy\kernel-work\results'

$env:PATH = "$sdk\bin;$sdk\lib\llvm\bin;$env:PATH"
$env:ROCM_PATH = $sdk; $env:HIP_PATH = $sdk
$env:HIP_DEVICE_LIB_PATH = "$sdk\lib\llvm\amdgcn\bitcode"
$env:HSA_OVERRIDE_GFX_VERSION = '11.5.1'

# ub, b, ctx, use-mtp
$arms = @(
    @{ ub = 16384; b = 16384; c = 8192;  mtp = $false; name = 'ub16k-c8k-nomtp' },
    @{ ub = 8192;  b = 8192;  c = 32768; mtp = $true;  name = 'ub8k-c32k-mtp' },
    @{ ub = 4096;  b = 4096;  c = 32768; mtp = $true;  name = 'ub4k-c32k-mtp' }
)

$rows = @()
foreach ($a in $arms) {
    Get-Process llama-server -ErrorAction SilentlyContinue | ForEach-Object { & taskkill /F /PID $_.Id 2>&1 | Out-Null }
    Start-Sleep -Seconds 5
    $o = Join-Path $res "fit16-$($a.name).out"
    $e = Join-Path $res "fit16-$($a.name).err"
    Remove-Item $o, $e -ErrorAction SilentlyContinue

    $args = @('-m', $model, '-dev', 'ROCm0', '-ngl', '99', '-fa', 'on', '-fit', 'off', '--load-mode', 'none',
              '-ctk', 'f16', '-ctv', 'f16', '-c', "$($a.c)", '-b', "$($a.b)", '-ub', "$($a.ub)",
              '--parallel', '1', '--host', '127.0.0.1', '--port', "$Port", '--no-webui', '--seed', '1234')
    if ($a.mtp) {
        $args += @('-md', $draft, '--jinja', '--spec-type', 'draft-mtp',
                   '--spec-draft-device', 'ROCm0', '--spec-draft-ngl', '99', '--spec-draft-n-max', '2')
    }
    $p = Start-Process -FilePath $bin -ArgumentList $args -PassThru -NoNewWindow `
                       -RedirectStandardOutput $o -RedirectStandardError $e
    Write-Output ("=== $($a.name): -ub $($a.ub) -b $($a.b) -c $($a.c) mtp=$($a.mtp) ===")

    $ready = $false
    $deadline = (Get-Date).AddSeconds(300)
    while ((Get-Date) -lt $deadline) {
        if ($p.HasExited) { break }
        if (Select-String -Path $e -Pattern 'listening on' -ErrorAction SilentlyContinue) { $ready = $true; break }
        Start-Sleep -Seconds 3
    }

    if ($ready) {
        Write-Output "  LOADED - measuring"
        try {
            $body = @{ prompt = 'Explain how a modern MoE transformer with gated linear attention processes a single decode step end to end, covering embedding lookup, the layer norm and projection GEMVs, top-k expert routing, the shared expert, the linear-attention recurrence, the KV read for full-attention layers, and the final norm and output projection.'; n_predict = 128; cache_prompt = $false; temperature = 0.0; top_k = 1; top_p = 1.0; min_p = 0.0; stream = $false } | ConvertTo-Json
            $r = Invoke-RestMethod -Uri "http://127.0.0.1:$Port/completion" -Method Post -Body $body -ContentType 'application/json' -TimeoutSec 1200
            $t = $r.timings
            Write-Output ("  PREFILL {0:N1} t/s   DECODE {1:N2} t/s   acc={2}/{3}" -f $t.prompt_per_second, $t.predicted_per_second, $t.draft_n_accepted, $t.draft_n)
            $rows += [pscustomobject]@{ arm = $a.name; loaded = $true; prefill = [math]::Round($t.prompt_per_second,1); decode = [math]::Round($t.predicted_per_second,2) }
        } catch {
            Write-Output "  request failed: $_"
            $rows += [pscustomobject]@{ arm = $a.name; loaded = $true; prefill = $null; decode = $null }
        }
    } else {
        $st = if ($p.HasExited) { 'EXITED (did not fit)' } else { 'HUNG' }
        Write-Output "  FAILED: $st"
        Select-String -Path $e -Pattern 'failed to allocate ROCm0 buffer of size (\d+)' -ErrorAction SilentlyContinue |
            Select-Object -First 1 | ForEach-Object {
                $need = [int64]$_.Matches[0].Groups[1].Value
                Write-Output ("    needed {0} bytes = {1:N2} GiB" -f $need, ($need / 1073741824.0))
            }
        $rows += [pscustomobject]@{ arm = $a.name; loaded = $false; prefill = $null; decode = $null }
    }
    if (-not $p.HasExited) { & taskkill /F /PID $p.Id 2>&1 | Out-Null }
    Start-Sleep -Seconds 3
}
Write-Output ''
$rows | Format-Table -AutoSize | Out-String | Write-Output
$rows | ConvertTo-Json -Depth 3 | Set-Content (Join-Path $res 'carve16-fit-tests.json')
Get-Process llama-server -ErrorAction SilentlyContinue | ForEach-Object { & taskkill /F /PID $_.Id 2>&1 | Out-Null }
