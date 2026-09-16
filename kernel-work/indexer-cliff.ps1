# indexer-cliff.ps1 — run the MTP acceptance sweep at three indexer.top_k values.
# Proves/moves the Bug B cliff (n_kv > top_k + ratio - 1) and tests whether raising it unlocks MTP.
$ErrorActionPreference = 'Continue'
$bin  = 'C:\AI\build\strix-llama-win\build-win\bin\llama-server.exe'
$rocm = 'C:\Program Files\AMD\ROCm\7.2'
$root = 'C:\Projects\REV-N-ornith-eval-20260911\kernel-work'
$res  = Join-Path $root 'results'
$mdl  = 'C:\AI\models\qwen38-flash\unsloth-UD-IQ4_XS\Qwen3.8-Flash-Next-UD-IQ4_XS-00001-of-00003.gguf'
$head = 'C:\AI\models\qwen38-flash\unsloth-UD-IQ4_XS\MTP\mtp-Qwen3.8-Flash-Next-shared-Q8_0.gguf'
$env:PATH = "$rocm\bin;$rocm\lib\llvm\bin;$env:PATH"
$env:GGML_HIP_ENABLE_UNIFIED_MEMORY = '1'
$env:HSA_OVERRIDE_GFX_VERSION = '11.5.1'

function RunCase($tag, $topk, $port) {
  Write-Output "==== $tag (indexer.top_k=$topk) ===="
  Get-Process llama-server -ErrorAction SilentlyContinue | Stop-Process -Force
  Start-Sleep -Seconds 3
  $args = @('-m',$mdl,'-dev','ROCm0','-ngl','999','-fa','on','-fit','off','--load-mode','none',
    '-ctk','f16','-ctv','f16','-c','32768','-b','2048','-ub','2048','--parallel','1','--jinja',
    '-md',$head,'--spec-type','draft-mtp','--spec-draft-n-max','2',
    '--host','127.0.0.1','--port',"$port",'--no-webui')
  if ($topk -gt 0) { $args += @('--override-kv', "qwen4exp.attention.indexer.top_k=int:$topk") }
  $p = Start-Process -FilePath $bin -ArgumentList $args -PassThru -RedirectStandardError (Join-Path $res "ix-$tag.err") -NoNewWindow
  for ($i=0; $i -lt 60; $i++) {
    try { if ((Invoke-WebRequest "http://127.0.0.1:$port/health" -TimeoutSec 3 -UseBasicParsing).StatusCode -eq 200) { break } } catch { Start-Sleep -Seconds 5 }
  }
  python "$root\indexer-test.py" $port $tag 2>&1 | Select-Object -Last 6
  Get-Process llama-server -ErrorAction SilentlyContinue | Stop-Process -Force
  Start-Sleep -Seconds 2
}

RunCase "topk-default-2048" 0    8200
RunCase "topk-512"          512  8201
RunCase "topk-8192"         8192 8202
Write-Output "==== indexer cliff test done ===="
