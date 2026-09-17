# compute-buffer-vs-ub.ps1 - the device compute buffer as a function of ubatch.
#
# The 0.5 GB carve fails on the WEIGHT buffer alone (66.01 GiB > 63.31 GiB ceiling), so
# no batch tuning can rescue it. The question that still matters is: how much carve is
# actually needed? That is weights (fixed, 66.01 GiB) + compute buffer (scales with ub)
# + KV. This measures the compute half.
#
# Weights are placed on the CPU with -ngl 20 so the device has room for the compute
# buffer, which is allocated on the GPU regardless of where the weights live. Sizes are
# read from ggml's own "compute buffer size" line, or its "failed to allocate ...
# buffer of size N" error, so a too-large ub still yields a number.
param([int[]]$UbList = @(512, 2048, 4096, 8192, 16384), [int]$Ngl = 20, [int]$Port = 8530)
$ErrorActionPreference = 'Continue'
$bin   = 'C:\AI\build\strix-llama-win\build-therock\bin\llama-server.exe'
$sdk   = 'C:\AI\sdk\therock1151'
$model = 'C:\AI\models\qwen38-flash\projfix\Qwen3.8-Flash-Next-IQ4_NL-PROJFIX-00001-of-00009.gguf'
$res   = 'C:\Projects\strix-alloy\kernel-work\results'

$env:PATH = "$sdk\bin;$sdk\lib\llvm\bin;$env:PATH"
$env:ROCM_PATH = $sdk; $env:HIP_PATH = $sdk
$env:HIP_DEVICE_LIB_PATH = "$sdk\lib\llvm\amdgcn\bitcode"
$env:HSA_OVERRIDE_GFX_VERSION = '11.5.1'

function Kill-Srv {
    Get-Process llama-server -ErrorAction SilentlyContinue | ForEach-Object { & taskkill /F /PID $_.Id 2>&1 | Out-Null }
    Start-Sleep -Seconds 4
}

$rows = @()
foreach ($ub in $UbList) {
    Kill-Srv
    $e = Join-Path $res "cbu-$ub.err"
    $o = Join-Path $res "cbu-$ub.out"
    Remove-Item $e, $o -ErrorAction SilentlyContinue

    # -fit off and an explicit -ngl keep this away from the fit probe, which hangs
    $a = @('-m', $model, '-dev', 'ROCm0', '-ngl', "$Ngl", '-fa', 'on', '-fit', 'off', '--load-mode', 'none',
           '-ctk', 'f16', '-ctv', 'f16', '-c', '32768', '-b', "$ub", '-ub', "$ub",
           '--parallel', '1', '--host', '127.0.0.1', '--port', "$Port", '--no-webui')
    $p = Start-Process -FilePath $bin -ArgumentList $a -PassThru -NoNewWindow `
                       -RedirectStandardOutput $o -RedirectStandardError $e

    $ready = $false
    $deadline = (Get-Date).AddSeconds(200)
    while ((Get-Date) -lt $deadline) {
        if ($p.HasExited) { break }
        if (Select-String -Path $e -Pattern 'listening on' -ErrorAction SilentlyContinue) { $ready = $true; break }
        Start-Sleep -Seconds 3
    }

    $bytes = $null; $src = ''
    # 1) friendly size line (successful allocation)
    $m1 = Select-String -Path $e -Pattern 'compute buffer size\s*=\s*([0-9]+(?:\.[0-9]+)?)\s*MiB' -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($m1) { $bytes = [int64]([double]$m1.Matches[0].Groups[1].Value * 1048576); $src = 'reported' }
    # 2) failure message (too big to allocate) - "failed to allocate ROCm0 buffer of size N"
    if (-not $bytes) {
        $m2 = Select-String -Path $e -Pattern 'failed to allocate ROCm0 buffer of size (\d+)' -ErrorAction SilentlyContinue | Select-Object -Last 1
        if ($m2) { $bytes = [int64]$m2.Matches[0].Groups[1].Value; $src = 'alloc-fail' }
    }
    # 3) raw allocating line as a last resort
    if (-not $bytes) {
        $m3 = Select-String -Path $e -Pattern 'allocating ([0-9]+(?:\.[0-9]+)?) MiB on device 0: cudaMalloc failed' -ErrorAction SilentlyContinue | Select-Object -Last 1
        if ($m3) { $bytes = [int64]([double]$m3.Matches[0].Groups[1].Value * 1048576); $src = 'raw-alloc' }
    }

    $state = if ($ready) { 'LOADED' } elseif ($p.HasExited) { 'exited' } else { 'HUNG' }
    if ($bytes) {
        $gib = [math]::Round($bytes / 1073741824.0, 2)
        Write-Output ("ub={0,6}  {1,-7}  compute ~{2,8} bytes = {3,6} GiB  [{4}]   weights(same fig as dev)= n/a" -f $ub, $state, $bytes, $gib, $src)
        $rows += [pscustomobject]@{ ub = $ub; state = $state; compute_gib = $gib; src = $src }
    } else {
        Write-Output ("ub={0,6}  {1,-7}  (no size found)" -f $ub, $state)
        $rows += [pscustomobject]@{ ub = $ub; state = $state; compute_gib = $null; src = '' }
    }
    if (-not $p.HasExited) { & taskkill /F /PID $p.Id 2>&1 | Out-Null }
    Start-Sleep -Seconds 2
}
Kill-Srv
Write-Output ''
Write-Output ("=== compute buffer vs ubatch (-ngl $Ngl, -c 32768, f16 KV) ===")
$rows | Format-Table -AutoSize | Out-String | Write-Output
Write-Output "weights are a separate fixed 66.01 GiB (70,874,867,968 B); device total = that + compute + KV"
$rows | ConvertTo-Json -Depth 3 | Set-Content (Join-Path $res 'compute-buffer-vs-ub.json')
