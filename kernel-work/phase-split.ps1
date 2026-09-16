# phase-split.ps1 — measure the target-decode vs spec-catchup split at n-max 1 and 2 (warm).
param(
  [int]$Ctx = 16384, [int]$B = 2048, [int]$Ub = 2048,
  [int]$Prompt = 8192, [int]$Gen = 256, [int]$Port = 8279
)
$ErrorActionPreference = 'Continue'
$bin  = 'C:\AI\build\strix-llama-win\build-therock\bin\llama-server.exe'
$sdk  = 'C:\AI\sdk\therock1151'
$root = 'C:\Projects\REV-N-ornith-eval-20260911\kernel-work'
$res  = Join-Path $root 'results'
$model = 'C:\AI\models\qwen38-flash\projfix\Qwen3.8-Flash-Next-IQ4_NL-PROJFIX-00001-of-00009.gguf'
$head  = 'C:\AI\models\qwen38-flash\projfix\mtp-Qwen3.8-Flash-Next-shared-Q8_0.gguf'
$blog  = Join-Path $res 'phase-split.log'

$env:PATH = "$sdk\bin;$sdk\lib\llvm\bin;$env:PATH"
$env:ROCM_PATH = $sdk; $env:HIP_PATH = $sdk
$env:HIP_DEVICE_LIB_PATH = "$sdk\lib\llvm\amdgcn\bitcode"
$env:GGML_HIP_ENABLE_UNIFIED_MEMORY = '1'
$env:HSA_OVERRIDE_GFX_VERSION = '11.5.1'

foreach ($nmax in @(1,2)) {
  Get-Process llama-server -ErrorAction SilentlyContinue | Stop-Process -Force
  Start-Sleep -Seconds 5
  $a = @('-m',$model,'-md',$head,'-dev','ROCm0','-ngl','999','-fa','on','-fit','off','--load-mode','none',
    '-ctk','f16','-ctv','f16','-c',"$Ctx",'-b',"$B",'-ub',"$Ub",'--parallel','1',
    '--host','127.0.0.1','--port',"$Port",'--no-webui','-lv','3',
    '--spec-type','draft-mtp','--spec-draft-n-max',"$nmax")
  $serr = Join-Path $res "ps-n$nmax.err"
  "==== phase-split n-max=$nmax $(Get-Date -Format o) ====" | Out-File $blog -Append -Encoding utf8
  $p = Start-Process -FilePath $bin -ArgumentList $a -PassThru -RedirectStandardOutput (Join-Path $res "ps-n$nmax.out") -RedirectStandardError $serr -NoNewWindow
  $ok=$false; $t0=Get-Date
  while (((Get-Date)-$t0).TotalSeconds -lt 900) {
    if ($p.HasExited) { "  EXITED $($p.ExitCode)" | Out-File $blog -Append -Encoding utf8; break }
    try { if ((Invoke-WebRequest "http://127.0.0.1:$Port/health" -TimeoutSec 5 -UseBasicParsing).StatusCode -eq 200) { $ok=$true; break } } catch { Start-Sleep -Seconds 5 }
  }
  if ($ok) {
    # warm pass, then the measured pass
    python "$root\fnbench.py" --port $Port --label "ps-warm-n$nmax" --sizes "$Prompt" --gen 64 --repeats 1 `
      --out (Join-Path $res "ps-warm-n$nmax.json") 2>&1 | Out-Null
    python "$root\fnbench.py" --port $Port --label "ps-n$nmax" --sizes "$Prompt" --gen $Gen --repeats 1 `
      --out (Join-Path $res "ps-n$nmax.json") 2>&1 | Tee-Object -FilePath $blog -Append
  }
  Start-Sleep -Seconds 2
  Get-Process llama-server -ErrorAction SilentlyContinue | Stop-Process -Force
  Start-Sleep -Seconds 3

  "--- phase lines n-max $nmax ---" | Out-File $blog -Append -Encoding utf8
  Get-Content $serr | Select-String -Pattern 'phase: tgt_decode|draft acceptance|statistics draft-mtp' |
    ForEach-Object { $_.Line } | Tee-Object -FilePath $blog -Append
}
"ALL DONE $(Get-Date -Format o)" | Out-File $blog -Append -Encoding utf8
