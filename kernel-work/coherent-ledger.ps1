# coherent-ledger.ps1 — ONE dataset per n-max at -lv 4, warm, so phase split and draft totals
# come from the SAME request. Mixing runs is what produced the earlier arithmetic slips.
param([int]$Prompt = 8192, [int]$Gen = 256, [int]$Port = 8281)
$ErrorActionPreference = 'Continue'
$bin  = 'C:\AI\build\strix-llama-win\build-therock\bin\llama-server.exe'
$sdk  = 'C:\AI\sdk\therock1151'
$root = 'C:\Projects\REV-N-ornith-eval-20260911\kernel-work'
$res  = Join-Path $root 'results'
$model = 'C:\AI\models\qwen38-flash\projfix\Qwen3.8-Flash-Next-IQ4_NL-PROJFIX-00001-of-00009.gguf'
$head  = 'C:\AI\models\qwen38-flash\projfix\mtp-Qwen3.8-Flash-Next-shared-Q8_0.gguf'
$blog  = Join-Path $res 'coherent-ledger.log'

$env:PATH = "$sdk\bin;$sdk\lib\llvm\bin;$env:PATH"
$env:ROCM_PATH = $sdk; $env:HIP_PATH = $sdk
$env:HIP_DEVICE_LIB_PATH = "$sdk\lib\llvm\amdgcn\bitcode"
$env:GGML_HIP_ENABLE_UNIFIED_MEMORY = '1'
$env:HSA_OVERRIDE_GFX_VERSION = '11.5.1'

foreach ($nmax in @(1,2)) {
  Get-Process llama-server -ErrorAction SilentlyContinue | Stop-Process -Force
  Start-Sleep -Seconds 5
  $a = @('-m',$model,'-md',$head,'-dev','ROCm0','-ngl','999','-fa','on','-fit','off','--load-mode','none',
    '-ctk','f16','-ctv','f16','-c','16384','-b','2048','-ub','2048','--parallel','1',
    '--host','127.0.0.1','--port',"$Port",'--no-webui','-lv','4',
    '--spec-type','draft-mtp','--spec-draft-n-max',"$nmax")
  $serr = Join-Path $res "cl-n$nmax.err"
  $p = Start-Process -FilePath $bin -ArgumentList $a -PassThru -RedirectStandardOutput (Join-Path $res "cl-n$nmax.out") -RedirectStandardError $serr -NoNewWindow
  $ok=$false; $t0=Get-Date
  while (((Get-Date)-$t0).TotalSeconds -lt 900) {
    if ($p.HasExited) { break }
    try { if ((Invoke-WebRequest "http://127.0.0.1:$Port/health" -TimeoutSec 5 -UseBasicParsing).StatusCode -eq 200) { $ok=$true; break } } catch { Start-Sleep -Seconds 5 }
  }
  if ($ok) {
    # warm pass first so the measured request runs against a warm page cache
    python "$root\fnbench.py" --port $Port --label "cl-warm-n$nmax" --sizes "$Prompt" --gen 64 --repeats 1 `
      --out (Join-Path $res "cl-warm-n$nmax.json") 2>&1 | Out-Null
    # mark the log so we can isolate the measured request's lines
    "########## MEASURED REQUEST n-max=$nmax $(Get-Date -Format o) ##########" |
      Add-Content -LiteralPath $serr -Encoding utf8
    $t_mark = (Get-Item $serr).Length
    python "$root\fnbench.py" --port $Port --label "cl-n$nmax" --sizes "$Prompt" --gen $Gen --repeats 1 `
      --out (Join-Path $res "cl-n$nmax.json") 2>&1 | Tee-Object -FilePath $blog -Append
  }
  Start-Sleep -Seconds 2
  Get-Process llama-server -ErrorAction SilentlyContinue | Stop-Process -Force
  Start-Sleep -Seconds 3

  "===== n-max $nmax =====" | Out-File $blog -Append -Encoding utf8
  Get-Content $serr | Select-String -Pattern 'phase: tgt_decode|statistics draft-mtp|draft acceptance' |
    ForEach-Object { $_.Line } | Tee-Object -FilePath $blog -Append
}
"ALL DONE $(Get-Date -Format o)" | Out-File $blog -Append -Encoding utf8
