# requires-Version 5.1
# op-timing-correct.ps1 — run the op-timing AGGREGATE path in ITS documented configuration:
#   LLAMA_OP_TIMING=1  AND  GGML_CUDA_DISABLE_GRAPHS=1
# Graphs off changes absolute throughput, so decode t/s from this run is NOT usable.
# What IS usable: per-op shares, i.e. where the GPU time goes inside one eval.
#
# VALIDATION GATE: if the summary is not non-zero, or the request errors, the run is INVALID
# and nothing from it may be quoted.
param([int]$Prompt = 1024, [int]$Gen = 256, [int]$Ctx = 4096, [int]$Port = 8287)
$ErrorActionPreference = 'Continue'
$bin  = 'C:\AI\build\strix-llama-win\build-therock\bin\llama-server.exe'
$sdk  = 'C:\AI\sdk\therock1151'
$root = 'C:\Projects\REV-N-ornith-eval-20260911\kernel-work'
$res  = Join-Path $root 'results'
$model = 'C:\AI\models\qwen38-flash\projfix\Qwen3.8-Flash-Next-IQ4_NL-PROJFIX-00001-of-00009.gguf'

Get-Process llama-server -ErrorAction SilentlyContinue | Stop-Process -Force
Start-Sleep -Seconds 4
$env:PATH = "$sdk\bin;$sdk\lib\llvm\bin;$env:PATH"
$env:ROCM_PATH = $sdk; $env:HIP_PATH = $sdk
$env:HIP_DEVICE_LIB_PATH = "$sdk\lib\llvm\amdgcn\bitcode"
$env:HSA_OVERRIDE_GFX_VERSION = '11.5.1'

# the DOCUMENTED configuration for the aggregate path
$env:LLAMA_OP_TIMING = '1'
$env:GGML_CUDA_DISABLE_GRAPHS = '1'
$env:LLAMA_OP_TIMING_EVERY = '16'
Remove-Item Env:\LLAMA_OP_TIMING_OPS -ErrorAction SilentlyContinue   # aggregate path has no op filter

$a = @('-m',$model,'-dev','ROCm0','-ngl','999','-fa','on','-fit','off','--load-mode','none',
  '-ctk','f16','-ctv','f16','-c',"$Ctx",'-b','2048','-ub','2048','--parallel','1',
  '--host','127.0.0.1','--port',"$Port",'--no-webui')
$serr = Join-Path $res 'opt-correct.err'; $sout = Join-Path $res 'opt-correct.out'
Remove-Item $serr,$sout -ErrorAction SilentlyContinue
$p = Start-Process -FilePath $bin -ArgumentList $a -PassThru -RedirectStandardOutput $sout -RedirectStandardError $serr -NoNewWindow
$ok=$false; $t0=Get-Date
while (((Get-Date)-$t0).TotalSeconds -lt 900) {
  if ($p.HasExited) { Write-Output "EXITED $($p.ExitCode)"; break }
  try { if ((Invoke-WebRequest "http://127.0.0.1:$Port/health" -TimeoutSec 5 -UseBasicParsing).StatusCode -eq 200) { $ok=$true; break } } catch { Start-Sleep -Seconds 5 }
}
if ($ok) {
  Write-Output "READY $([int]((Get-Date)-$t0).TotalSeconds)s"
  python "$root\fnbench.py" --port $Port --label 'opt-correct' --sizes "$Prompt" --gen $Gen --repeats 1 --out (Join-Path $res 'opt-correct.json') 2>&1 |
    Select-String -Pattern 'n=|decode|error'
}
Start-Sleep -Seconds 2
Get-Process llama-server -ErrorAction SilentlyContinue | Stop-Process -Force
Start-Sleep -Seconds 3

$t = ''
try { $t = [IO.File]::ReadAllText($serr) } catch {}
$lines = ($t -replace "`r",'') -split "`n"
Write-Output ''
Write-Output '=== VALIDATION ==='
$headers = ($lines | Where-Object { $_ -match 'OP_TIMING' }).Count
Write-Output ("  OP_TIMING summary lines      = {0}" -f $headers)
$zero = ($lines | Where-Object { $_ -match 'total=\s+0\.0ms' }).Count
Write-Output ("  zero-total row lines          = {0}" -f $zero)
$errLines = ($lines | Where-Object { $_ -match 'ROCm error|GET_ROWS failed|abort|assert' }).Count
Write-Output ("  error lines                   = {0}" -f $errLines)
$valid = ($headers -gt 0) -and ($zero -eq 0) -and ($errLines -eq 0)
Write-Output ''
if ($valid) { Write-Output '  RUN VALID -> per-op shares may be read from parse-optiming.ps1' }
else        { Write-Output '  RUN INVALID -> do NOT quote any number from this run' }
