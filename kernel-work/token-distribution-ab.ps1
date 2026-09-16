# token-distribution-ab.ps1 - does the llama-bench token stream change prefill speed?
#
# Motivation: llama-bench feeds `std::rand() % n_vocab`. The Windows UCRT has RAND_MAX =
# 32767, so against this 248320-token vocabulary only the first 13.2% of IDs are reachable
# (verified with rand-check.c). A Linux/glibc build reaches all of them. Before attributing
# any of the cross-platform prefill gap to that, test whether the distribution matters at
# all, holding harness and engine constant.
param(
    [int]$Ctx = 32768,
    [int]$Port = 8700,
    [int]$Gen = 128,
    [int]$Repeats = 3,
    [string]$Sizes = '8192,16384'
)
$ErrorActionPreference = 'Continue'
$bin   = 'C:\AI\build\strix-llama-win\build-therock\bin\llama-server.exe'
$sdk   = 'C:\AI\sdk\therock1151'
$model = 'C:\AI\models\qwen38-flash\projfix\Qwen3.8-Flash-Next-IQ4_NL-PROJFIX-00001-of-00009.gguf'
$root  = 'C:\Projects\strix-alloy-clean\kernel-work'
$res   = Join-Path $root 'results'
New-Item -ItemType Directory -Force -Path $res | Out-Null

Get-Process llama-server -ErrorAction SilentlyContinue | ForEach-Object { & taskkill /F /T /PID $_.Id 2>&1 | Out-Null }
Start-Sleep -Seconds 5
$env:PATH = "$sdk\bin;$sdk\lib\llvm\bin;$env:PATH"
$env:ROCM_PATH = $sdk; $env:HIP_PATH = $sdk
$env:HIP_DEVICE_LIB_PATH = "$sdk\lib\llvm\amdgcn\bitcode"
$env:HSA_OVERRIDE_GFX_VERSION = '11.5.1'

$o = Join-Path $res 'tokdist.out'; $e = Join-Path $res 'tokdist.err'
Remove-Item $o, $e -ErrorAction SilentlyContinue
$a = @('-m', $model, '-dev', 'ROCm0', '-ngl', '99', '-fa', 'on', '-fit', 'off', '--load-mode', 'none',
       '-ctk', 'f16', '-ctv', 'f16', '-c', "$Ctx", '-b', '16384', '-ub', '16384',
       '--parallel', '1', '--host', '127.0.0.1', '--port', "$Port", '--no-webui', '--seed', '1234')
$p = Start-Process -FilePath $bin -ArgumentList $a -PassThru -NoNewWindow `
                   -RedirectStandardOutput $o -RedirectStandardError $e
Write-Output 'loading...'
$ok = $false; $t0 = Get-Date
while (((Get-Date) - $t0).TotalSeconds -lt 600) {
    if ($p.HasExited) { break }
    try { if ((Invoke-WebRequest "http://127.0.0.1:$Port/health" -TimeoutSec 5 -UseBasicParsing).StatusCode -eq 200) { $ok = $true; break } } catch { Start-Sleep -Seconds 4 }
}
if (-not $ok) {
    Write-Output 'NOT READY'
    Get-Content $e -Tail 10
    exit 1
}
Write-Output ("ready in {0}s" -f [int]((Get-Date)-$t0).TotalSeconds)

python "$root\token-distribution-test.py" --port $Port --sizes $Sizes --gen $Gen --repeats $Repeats `
    --out (Join-Path $res 'token-distribution.json') 2>&1 | ForEach-Object { Write-Output $_ }

& taskkill /F /T /PID $p.Id 2>&1 | Out-Null
Write-Output 'done'
