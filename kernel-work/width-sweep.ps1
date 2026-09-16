#requires -Version 5.1
# width-sweep.ps1 — round cost vs verification width (n-max 1/2/3), same prompt, same server.
# Cheap bound on the marginal cost of an extra verified row WITHOUT a replay harness:
#   round(w) = dense + experts(w rows) + attention(w rows) + other
# Differencing across w gives the marginal row cost, and the intercept bounds the
# width-independent (dense + other) part.
param([int]$Ctx = 32768, [int]$Gen = 384, [int]$Prompt = 8192, [int]$Port = 8298)
$ErrorActionPreference = 'Continue'
$bin  = 'C:\AI\build\strix-llama-win\build-therock\bin\llama-server.exe'
$sdk  = 'C:\AI\sdk\therock1151'
$root = 'C:\Projects\REV-N-ornith-eval-20260911\kernel-work'
$res  = Join-Path $root 'results'
$model = 'C:\AI\models\qwen38-flash\projfix\Qwen3.8-Flash-Next-IQ4_NL-PROJFIX-00001-of-00009.gguf'
$head  = 'C:\AI\models\qwen38-flash\projfix\mtp-Qwen3.8-Flash-Next-shared-Q8_0.gguf'
$blog  = Join-Path $res 'width-sweep.log'

$env:PATH = "$sdk\bin;$sdk\lib\llvm\bin;$env:PATH"
$env:ROCM_PATH = $sdk; $env:HIP_PATH = $sdk
$env:HIP_DEVICE_LIB_PATH = "$sdk\lib\llvm\amdgcn\bitcode"
$env:HSA_OVERRIDE_GFX_VERSION = '11.5.1'

foreach ($nmax in @(1,2,3)) {
  Get-Process llama-server -ErrorAction SilentlyContinue | Stop-Process -Force
  Start-Sleep -Seconds 5
  $a = @('-m',$model,'-md',$head,'-dev','ROCm0','-ngl','999','-fa','on','-fit','off','--load-mode','none',
    '-ctk','f16','-ctv','f16','-c',"$Ctx",'-b','2048','-ub','2048','--parallel','1',
    '--host','127.0.0.1','--port',"$Port",'--no-webui',
    '--spec-type','draft-mtp','--spec-draft-n-max',"$nmax")
  $serr = Join-Path $res "ws-n$nmax.err"
  Remove-Item $serr -ErrorAction SilentlyContinue
  "==== n-max $nmax $(Get-Date -Format o) ====" | Out-File $blog -Append -Encoding utf8
  $p = Start-Process -FilePath $bin -ArgumentList $a -PassThru -RedirectStandardOutput (Join-Path $res "ws-n$nmax.out") -RedirectStandardError $serr -NoNewWindow
  $ok=$false; $t0=Get-Date
  while (((Get-Date)-$t0).TotalSeconds -lt 900) {
    if ($p.HasExited) { "  EXITED $($p.ExitCode)" | Out-File $blog -Append -Encoding utf8; break }
    try { if ((Invoke-WebRequest "http://127.0.0.1:$Port/health" -TimeoutSec 5 -UseBasicParsing).StatusCode -eq 200) { $ok=$true; break } } catch { Start-Sleep -Seconds 5 }
  }
  if ($ok) {
    # warm pass first so rep0 is page-cache warm
    python "$root\fnbench.py" --port $Port --label "ws-warm-n$nmax" --sizes "$Prompt" --gen 64 --repeats 1 --out (Join-Path $res "ws-warm-n$nmax.json") 2>&1 | Out-Null
    python "$root\fnbench.py" --port $Port --label "ws-n$nmax" --sizes "$Prompt" --gen $Gen --repeats 1 --out (Join-Path $res "ws-n$nmax.json") 2>&1 | Tee-Object -FilePath $blog -Append
    $lines = @()
    try { $lines = ([IO.File]::ReadAllText($serr) -replace "`r",'') -split "`n" } catch {}
    foreach ($l in ($lines | Where-Object { $_ -match 'rounds:|target_ms|draft acceptance' })) {
      "  " + $l.Trim() | Out-File $blog -Append -Encoding utf8
    }
  }
  Start-Sleep -Seconds 2
  Get-Process llama-server -ErrorAction SilentlyContinue | Stop-Process -Force
  Start-Sleep -Seconds 3
}
"ALL DONE $(Get-Date -Format o)" | Out-File $blog -Append -Encoding utf8
