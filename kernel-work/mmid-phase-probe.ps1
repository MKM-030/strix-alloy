# mmid-phase-probe.ps1 - does MMID_512 execute during SERIAL DECODE, or only prefill?
#
# The earlier coverage evidence recorded an n_tokens=20 hit, which is a prefill batch. That does
# not establish that serial decode (n_tokens==1) reaches the helper. This runs a decode-heavy
# request and a prefill-heavy request against a build instrumented to count calls by token width,
# so the claim becomes provable rather than assumed.
param([int]$Port = 8720)
$ErrorActionPreference = 'Continue'
$bin  = 'C:\AI\build\strix-llama-win\build-therock\bin\llama-server.exe'
$sdk  = 'C:\AI\sdk\therock1151'
$model = 'C:\AI\models\qwen38-flash\projfix\Qwen3.8-Flash-Next-IQ4_NL-PROJFIX-00001-of-00009.gguf'
$res  = 'C:\Projects\strix-alloy\kernel-work\results'

Get-Process llama-server -ErrorAction SilentlyContinue | ForEach-Object { & taskkill /F /T /PID $_.Id 2>&1 | Out-Null }
Start-Sleep -Seconds 5
$env:PATH = "$sdk\bin;$sdk\lib\llvm\bin;$env:PATH"
$env:ROCM_PATH = $sdk; $env:HIP_PATH = $sdk
$env:HIP_DEVICE_LIB_PATH = "$sdk\lib\llvm\amdgcn\bitcode"
$env:HSA_OVERRIDE_GFX_VERSION = '11.5.1'

$o = Join-Path $res 'phase.out'; $e = Join-Path $res 'phase.err'
Remove-Item $o, $e -ErrorAction SilentlyContinue
$a = @('-m', $model, '-dev', 'ROCm0', '-ngl', '99', '-fa', 'on', '-fit', 'off', '--load-mode', 'none',
       '-ctk', 'f16', '-ctv', 'f16', '-c', '8192', '-b', '2048', '-ub', '2048',
       '--parallel', '1', '--host', '127.0.0.1', '--port', "$Port", '--no-webui', '--seed', '1234')
$p = Start-Process -FilePath $bin -ArgumentList $a -PassThru -NoNewWindow `
                   -RedirectStandardOutput $o -RedirectStandardError $e
$ok = $false; $t0 = Get-Date
while (((Get-Date) - $t0).TotalSeconds -lt 600) {
    if ($p.HasExited) { break }
    try { if ((Invoke-WebRequest "http://127.0.0.1:$Port/health" -TimeoutSec 5 -UseBasicParsing).StatusCode -eq 200) { $ok = $true; break } } catch { Start-Sleep -Seconds 4 }
}
Write-Output ("ready={0}" -f $ok)
if ($ok) {
    $mark = (Get-Item $e).Length
    Write-Output '--- decode-heavy: short prompt, 200 generated (forces n_tokens==1 steps) ---'
    $b1 = @{ prompt = 'Explain mixture-of-experts routing in detail.'; n_predict = 200; cache_prompt = $false
             temperature = 0.0; top_k = 1; top_p = 1.0; min_p = 0.0; stream = $false } | ConvertTo-Json
    $r1 = Invoke-RestMethod -Uri "http://127.0.0.1:$Port/completion" -Method Post -Body $b1 -ContentType 'application/json' -TimeoutSec 900
    Write-Output ("  prompt_n={0} predicted_n={1}" -f $r1.timings.prompt_n, $r1.timings.predicted_n)

    Write-Output '--- prefill-heavy: ~4000 prompt tokens, 8 generated ---'
    $long = ('The system measures each stage and records throughput carefully. ' * 400)
    $b2 = @{ prompt = $long; n_predict = 8; cache_prompt = $false
             temperature = 0.0; top_k = 1; top_p = 1.0; min_p = 0.0; stream = $false } | ConvertTo-Json
    $r2 = Invoke-RestMethod -Uri "http://127.0.0.1:$Port/completion" -Method Post -Body $b2 -ContentType 'application/json' -TimeoutSec 900
    Write-Output ("  prompt_n={0} predicted_n={1}" -f $r2.timings.prompt_n, $r2.timings.predicted_n)
}
& taskkill /F /T /PID $p.Id 2>&1 | Out-Null
Start-Sleep -Seconds 2
Write-Output ''
Write-Output '=== MMID512-PHASE probe lines ==='
$m = Select-String -Path $e -Pattern 'MMID512-PHASE'
Write-Output ("  total lines: {0}" -f $m.Count)
$m | Select-Object -First 3 | ForEach-Object { Write-Output ('  ' + $_.Line.Trim()) }
Write-Output '  ...'
$m | Select-Object -Last 2 | ForEach-Object { Write-Output ('  ' + $_.Line.Trim()) }
