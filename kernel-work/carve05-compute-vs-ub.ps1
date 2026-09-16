# carve05-compute-vs-ub.ps1 - how much device memory does the COMPUTE buffer need?
#
# The weight buffer is 66.01 GiB, but serving also needs a compute buffer whose size
# scales with the ubatch. At ub 16384 it is ~32.3 GiB, which is why the production
# config needs a 96 GB carve. This measures the requested compute size per ubatch.
#
# Reads the size from ggml's own failure message ("failed to allocate ROCm0 buffer of
# size N") so it works even when the allocation fails -- which is the case at the
# 0.5 GB carve. --fit on is used so the weights are reduced to fit and execution
# reaches the compute-buffer reservation.
param([int[]]$UbList = @(512, 1024, 2048, 4096, 8192, 16384), [int]$Port = 8520)
$ErrorActionPreference = 'Continue'
$bin   = 'C:\AI\build\strix-llama-win\build-therock\bin\llama-server.exe'
$sdk   = 'C:\AI\sdk\therock1151'
$model = 'C:\AI\models\qwen38-flash\projfix\Qwen3.8-Flash-Next-IQ4_NL-PROJFIX-00001-of-00009.gguf'
$res   = 'C:\Projects\strix-alloy\kernel-work\results'

$env:PATH = "$sdk\bin;$sdk\lib\llvm\bin;$env:PATH"
$env:ROCM_PATH = $sdk; $env:HIP_PATH = $sdk
$env:HIP_DEVICE_LIB_PATH = "$sdk\lib\llvm\amdgcn\bitcode"
$env:HSA_OVERRIDE_GFX_VERSION = '11.5.1'

$rows = @()
foreach ($ub in $UbList) {
    Get-Process llama-server -ErrorAction SilentlyContinue | ForEach-Object { & taskkill /F /PID $_.Id 2>&1 | Out-Null }
    Start-Sleep -Seconds 4
    $e = Join-Path $res "cvu-$ub.err"
    $o = Join-Path $res "cvu-$ub.out"
    Remove-Item $e, $o -ErrorAction SilentlyContinue

    $a = @('-m', $model, '-dev', 'ROCm0', '-fa', 'on', '-fit', 'on', '--load-mode', 'none',
           '-ctk', 'f16', '-ctv', 'f16', '-c', '32768', '-b', "$ub", '-ub', "$ub",
           '--parallel', '1', '--host', '127.0.0.1', '--port', "$Port", '--no-webui')
    $p = Start-Process -FilePath $bin -ArgumentList $a -PassThru -NoNewWindow `
                       -RedirectStandardOutput $o -RedirectStandardError $e
    $ready = $false
    $deadline = (Get-Date).AddSeconds(240)
    while ((Get-Date) -lt $deadline) {
        if ($p.HasExited) { break }
        if (Select-String -Path $e -Pattern 'listening on' -ErrorAction SilentlyContinue) { $ready = $true; break }
        Start-Sleep -Seconds 3
    }

    # compute buffer request appears as "failed to allocate ROCm0 buffer of size N" or as a
    # successful "ROCm0 compute buffer size = X MiB" line
    $need = $null; $status = 'UNKNOWN'
    if ($ready) { $status = 'LOADED' }
    $m = Select-String -Path $e -Pattern 'failed to allocate ROCm0 buffer of size (\d+)' -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($m) { $need = [int64]$m.Matches[0].Groups[1].Value }
    $m2 = Select-String -Path $e -Pattern 'allocating (\d+\.?\d*) MiB on device' -ErrorAction SilentlyContinue | Select-Object -First 1
    $wreq = if ($m2) { $m2.Matches[0].Groups[1].Value } else { $null }

    if ($need) {
        $gib = [math]::Round($need / 1073741824.0, 2)
        Write-Output ("ub={0,6}  {1,-8}  compute wants {2,8} bytes = {3,6} GiB   (device alloc attempt: {4})" -f $ub, $status, $need, $gib, $wreq)
        $rows += [pscustomobject]@{ ub = $ub; status = $status; compute_gib = $gib }
    } else {
        Write-Output ("ub={0,6}  {1,-8}  (no explicit compute size; device alloc attempt: {2})" -f $ub, $status, $wreq)
        $rows += [pscustomobject]@{ ub = $ub; status = $status; compute_gib = $null }
    }
    if (-not $p.HasExited) { & taskkill /F /PID $p.Id 2>&1 | Out-Null }
    Start-Sleep -Seconds 2
}
Get-Process llama-server -ErrorAction SilentlyContinue | ForEach-Object { & taskkill /F /PID $_.Id 2>&1 | Out-Null }
Write-Output ''
$rows | Format-Table -AutoSize | Out-String | Write-Output
$rows | ConvertTo-Json -Depth 3 | Set-Content (Join-Path $res 'carve05-compute-vs-ub.json')
