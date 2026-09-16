#requires -Version 5.1
# expert-ablation.ps1 — how much of a decode round is the routed-expert path?
#
# Codex proposed a routed-output replay harness (60-90 min) to measure this. A cheaper decisive
# proxy: change n_expert_used and see whether round time tracks expert bytes.
#   expert bytes scale with n_expert_used (top-k); everything else stays fixed.
#   If time falls proportionally -> the round is expert-bandwidth-bound.
#   If time barely moves       -> the round is dominated by non-expert work.
#
# LABEL IT CORRECTLY: this is a REDUCED-MODEL ablation (fewer experts = different model output).
# It is an attribution experiment, NOT an optimization of the original model. Acceptance and
# quality change; only the TIMING delta is meaningful.
param([int]$Ctx = 32768, [int]$Gen = 384, [int]$Prompt = 8192, [int]$Nmax = 2, [int]$Port = 8299)
$ErrorActionPreference = 'Continue'
$bin  = 'C:\AI\build\strix-llama-win\build-therock\bin\llama-server.exe'
$sdk  = 'C:\AI\sdk\therock1151'
$root = 'C:\Projects\REV-N-ornith-eval-20260911\kernel-work'
$res  = Join-Path $root 'results'
$model = 'C:\AI\models\qwen38-flash\projfix\Qwen3.8-Flash-Next-IQ4_NL-PROJFIX-00001-of-00009.gguf'
$head  = 'C:\AI\models\qwen38-flash\projfix\mtp-Qwen3.8-Flash-Next-shared-Q8_0.gguf'
$blog  = Join-Path $res 'expert-ablation.log'

$env:PATH = "$sdk\bin;$sdk\lib\llvm\bin;$env:PATH"
$env:ROCM_PATH = $sdk; $env:HIP_PATH = $sdk
$env:HIP_DEVICE_LIB_PATH = "$sdk\lib\llvm\amdgcn\bitcode"
$env:GGML_HIP_ENABLE_UNIFIED_MEMORY = '1'
$env:HSA_OVERRIDE_GFX_VERSION = '11.5.1'

# top-k values to test: baseline 10, then halves
foreach ($k in @(10, 5, 3)) {
  Get-Process llama-server -ErrorAction SilentlyContinue | Stop-Process -Force
  Start-Sleep -Seconds 5
  $a = @('-m',$model,'-md',$head,'-dev','ROCm0','-ngl','999','-fa','on','-fit','off','--load-mode','none',
    '-ctk','f16','-ctv','f16','-c',"$Ctx",'-b','2048','-ub','2048','--parallel','1',
    '--host','127.0.0.1','--port',"$Port",'--no-webui',
    '--spec-type','draft-mtp','--spec-draft-n-max',"$Nmax")
  if ($k -ne 10) {
    $a += @('--override-kv', "qwen4exp.expert_used_count=int:$k")
  }
  $serr = Join-Path $res "ea-k$k.err"
  Remove-Item $serr -ErrorAction SilentlyContinue
  "==== expert_used_count=$k  (n-max $Nmax)  $(Get-Date -Format o) ====" | Out-File $blog -Append -Encoding utf8
  $p = Start-Process -FilePath $bin -ArgumentList $a -PassThru -RedirectStandardOutput (Join-Path $res "ea-k$k.out") -RedirectStandardError $serr -NoNewWindow
  $ok=$false; $t0=Get-Date
  while (((Get-Date)-$t0).TotalSeconds -lt 900) {
    if ($p.HasExited) { "  EXITED $($p.ExitCode)" | Out-File $blog -Append -Encoding utf8; break }
    try { if ((Invoke-WebRequest "http://127.0.0.1:$Port/health" -TimeoutSec 5 -UseBasicParsing).StatusCode -eq 200) { $ok=$true; break } } catch { Start-Sleep -Seconds 5 }
  }
  if ($ok) {
    # warm pass FIRST: rep0 is page-cache cold (96 GB of weights), which inflates round cost badly.
    python "$root\fnbench.py" --port $Port --label "ea-warm-k$k" --sizes "$Prompt" --gen 64 --repeats 1 --out (Join-Path $res "ea-warm-k$k.json") 2>&1 | Out-Null
    python "$root\fnbench.py" --port $Port --label "ea-k$k" --sizes "$Prompt" --gen $Gen --repeats 2 --out (Join-Path $res "ea-k$k.json") 2>&1 | Tee-Object -FilePath $blog -Append
    $lines = @()
    try { $lines = ([IO.File]::ReadAllText($serr) -replace "`r",'') -split "`n" } catch {}
    foreach ($l in ($lines | Where-Object { $_ -match 'expert_used|rounds:|target_ms|draft acceptance' })) {
      "  " + $l.Trim() | Out-File $blog -Append -Encoding utf8
    }
  }
  Start-Sleep -Seconds 2
  Get-Process llama-server -ErrorAction SilentlyContinue | Stop-Process -Force
  Start-Sleep -Seconds 3
}
"ALL DONE $(Get-Date -Format o)" | Out-File $blog -Append -Encoding utf8
