#requires -Version 5.1
# ig-diag.ps1 — run with LLAMA_OP_TIMING=2 (graphs ON) and capture the diagnostic output.
param([int]$Prompt = 1024, [int]$Gen = 256, [int]$Ctx = 4096, [int]$Port = 8289)
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

$env:LLAMA_OP_TIMING = '2'
Remove-Item Env:\GGML_CUDA_DISABLE_GRAPHS -ErrorAction SilentlyContinue
$env:LLAMA_OP_TIMING_EVERY = '8'
# start NARROW so a huge filter is not a confound
$env:LLAMA_OP_TIMING_OPS = 'mul_mat_id'

$a = @('-m',$model,'-dev','ROCm0','-ngl','999','-fa','on','-fit','off','--load-mode','none',
  '-ctk','f16','-ctv','f16','-c',"$Ctx",'-b','2048','-ub','2048','--parallel','1',
  '--host','127.0.0.1','--port',"$Port",'--no-webui')
$serr = Join-Path $res 'ig-diag.err'; $sout = Join-Path $res 'ig-diag.out'
Remove-Item $serr,$sout -ErrorAction SilentlyContinue
$p = Start-Process -FilePath $bin -ArgumentList $a -PassThru -RedirectStandardOutput $sout -RedirectStandardError $serr -NoNewWindow
$ok=$false; $t0=Get-Date
while (((Get-Date)-$t0).TotalSeconds -lt 900) {
  if ($p.HasExited) { Write-Output "EXITED $($p.ExitCode)"; break }
  try { if ((Invoke-WebRequest "http://127.0.0.1:$Port/health" -TimeoutSec 5 -UseBasicParsing).StatusCode -eq 200) { $ok=$true; break } } catch { Start-Sleep -Seconds 5 }
}
if ($ok) {
  Write-Output "READY $([int]((Get-Date)-$t0).TotalSeconds)s"
  python "$root\fnbench.py" --port $Port --label 'ig-diag' --sizes "$Prompt" --gen $Gen --repeats 1 --out (Join-Path $res 'ig-diag.json') 2>&1 |
    Select-String -Pattern 'n=|error'
}
Start-Sleep -Seconds 2
Get-Process llama-server -ErrorAction SilentlyContinue | Stop-Process -Force
Start-Sleep -Seconds 3

Write-Output ''
Write-Output '=== DIAGNOSTIC LINES ==='
$t = ''
try { $t = [IO.File]::ReadAllText($serr) } catch {}
$lines = ($t -replace "`r", '') -split "`n"
foreach ($l in ($lines | Where-Object { $_ -match 'OP_TIMING_IG DIAG|OP_TIMING_IG after|tracked total' } | Select-Object -First 25)) {
  Write-Output ("  " + $l.TrimEnd())
}
Write-Output ''
Write-Output '=== errors ==='
foreach ($l in ($lines | Where-Object { $_ -match 'ROCm error|failed|abort' } | Select-Object -First 6)) {
  Write-Output ("  " + $l.Trim())
}
