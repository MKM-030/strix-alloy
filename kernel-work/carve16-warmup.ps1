# carve16-warmup.ps1 - is the 86 t/s a cold-cache artifact or structural?
#
# At the current carve the model LOADS but prefill measured 86.2 t/s against a
# production 1031. Two very different explanations:
#   (a) cold cache - the PLE table and weights stream off disk on the first request,
#       so later requests should recover toward ~1000 t/s;
#   (b) structural - the weight set (66.01 GiB) exceeds the carve's device pool
#       (63.16 GiB), so part of it is never resident and every request pays for it.
# Repeated identical requests separate the two: (a) converges, (b) flatlines.
param([int]$Port = 8550, [int]$Reps = 4)
$ErrorActionPreference = 'Continue'
$bin   = 'C:\AI\build\strix-llama-win\build-therock\bin\llama-server.exe'
$sdk   = 'C:\AI\sdk\therock1151'
$model = 'C:\AI\models\qwen38-flash\projfix\Qwen3.8-Flash-Next-IQ4_NL-PROJFIX-00001-of-00009.gguf'
$res   = 'C:\Projects\strix-alloy\kernel-work\results'

$env:PATH = "$sdk\bin;$sdk\lib\llvm\bin;$env:PATH"
$env:ROCM_PATH = $sdk; $env:HIP_PATH = $sdk
$env:HIP_DEVICE_LIB_PATH = "$sdk\lib\llvm\amdgcn\bitcode"
$env:HSA_OVERRIDE_GFX_VERSION = '11.5.1'

Get-Process llama-server -ErrorAction SilentlyContinue | ForEach-Object { & taskkill /F /PID $_.Id 2>&1 | Out-Null }
Start-Sleep -Seconds 5

$o = Join-Path $res 'warm16.out'
$e = Join-Path $res 'warm16.err'
Remove-Item $o, $e -ErrorAction SilentlyContinue

# the config that loaded at this carve: ub 16384, small -c to fit the compute buffer
$a = @('-m', $model, '-dev', 'ROCm0', '-ngl', '99', '-fa', 'on', '-fit', 'off', '--load-mode', 'none',
       '-ctk', 'f16', '-ctv', 'f16', '-c', '8192', '-b', '16384', '-ub', '16384',
       '--parallel', '1', '--host', '127.0.0.1', '--port', "$Port", '--no-webui', '--seed', '1234')
$p = Start-Process -FilePath $bin -ArgumentList $a -PassThru -NoNewWindow `
                   -RedirectStandardOutput $o -RedirectStandardError $e
Write-Output "loading (this takes minutes at this carve)..."
$ready = $false
$deadline = (Get-Date).AddSeconds(1500)
while ((Get-Date) -lt $deadline) {
    if ($p.HasExited) { break }
    if (Select-String -Path $e -Pattern 'listening on' -ErrorAction SilentlyContinue) { $ready = $true; break }
    Start-Sleep -Seconds 5
}
if (-not $ready) {
    Write-Output "DID NOT LOAD"
    Select-String -Path $e -Pattern 'failed to allocate|ROCm error|out of memory' | Select-Object -Last 3 |
        ForEach-Object { Write-Output ('  ' + $_.Line.Trim()) }
} else {
    Write-Output "loaded; sending $Reps identical requests"
    for ($i = 1; $i -le $Reps; $i++) {
        try {
            $body = @{ prompt = 'Explain how a modern MoE transformer with gated linear attention processes a single decode step end to end, covering embedding lookup, the layer norm and projection GEMVs, top-k expert routing, the shared expert, the linear-attention recurrence, the KV read for full-attention layers, and the final norm and output projection.'; n_predict = 128; cache_prompt = $false; temperature = 0.0; top_k = 1; top_p = 1.0; min_p = 0.0; stream = $false } | ConvertTo-Json
            $r = Invoke-RestMethod -Uri "http://127.0.0.1:$Port/completion" -Method Post -Body $body -ContentType 'application/json' -TimeoutSec 2400
            $t = $r.timings
            Write-Output ("  rep $i : PREFILL {0,8:N1} t/s   DECODE {1,6:N2} t/s   (prompt_n={2})" -f $t.prompt_per_second, $t.predicted_per_second, $t.prompt_n)
        } catch {
            Write-Output "  rep $i : failed - $_"
        }
    }
}
if (-not $p.HasExited) { & taskkill /F /PID $p.Id 2>&1 | Out-Null }
Write-Output ''
Write-Output "production at the 96 GB carve: prefill 1031 t/s, decode 34 t/s"
