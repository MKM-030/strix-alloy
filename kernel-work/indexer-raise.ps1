# indexer-raise.ps1 — does raising indexer.top_k push the MTP acceptance cliff out far enough to matter?
# Also tests the dense draft (top_k hugely raised) as the "keep draft dense" hypothesis.
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
  Start-Sleep -Seconds 4
  $a = @('-m',$mdl,'-dev','ROCm0','-ngl','999','-fa','on','-fit','off','--load-mode','none',
    '-ctk','f16','-ctv','f16','-c','16384','-b','2048','-ub','2048','--parallel','1','--jinja',
    '-md',$head,'--spec-type','draft-mtp','--spec-draft-n-max','2',
    '--host','127.0.0.1','--port',"$port",'--no-webui')
  if ($topk -gt 0) { $a += @('--override-kv', "qwen4exp.attention.indexer.top_k=int:$topk") }
  $p = Start-Process -FilePath $bin -ArgumentList $a -PassThru -RedirectStandardError (Join-Path $res "ir-$tag.err") -NoNewWindow
  $up = $false
  for ($i=0; $i -lt 48; $i++) {
    if ($p.HasExited) { break }
    try { if ((Invoke-WebRequest "http://127.0.0.1:$port/health" -TimeoutSec 3 -UseBasicParsing).StatusCode -eq 200) { $up = $true; break } } catch { Start-Sleep -Seconds 5 }
  }
  if (-not $up) {
    Write-Output "  FAILED TO START: $((Get-Content (Join-Path $res "ir-$tag.err") -Tail 2) -join ' ')"
  } else {
    python "$root\indexer-test.py" $port $tag 2>&1 | Select-Object -Last 6
  }
  Get-Process llama-server -ErrorAction SilentlyContinue | Stop-Process -Force
  Start-Sleep -Seconds 2
}

RunCase "topk-4096" 4096 8210
RunCase "topk-8192b" 8192 8211
RunCase "topk-16384" 16384 8212
Write-Output "==== raise test done ===="
