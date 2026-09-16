# topk-sweet.ps1 — find a top_k that keeps the draft dense enough for acceptance but does not blow
# the indexer allocation at depth. Test top_k = ctx + margin, at increasing ctx.
$ErrorActionPreference = 'Continue'
$bin  = 'C:\AI\build\strix-llama-win\build-win\bin\llama-server.exe'
$rocm = 'C:\Program Files\AMD\ROCm\7.2'
$root = 'C:\Projects\REV-N-ornith-eval-20260911\kernel-work'
$res  = Join-Path $root 'results'
$ud   = 'C:\AI\models\qwen38-flash\unsloth-UD-IQ4_XS\Qwen3.8-Flash-Next-UD-IQ4_XS-00001-of-00003.gguf'
$head = 'C:\AI\models\qwen38-flash\unsloth-UD-IQ4_XS\MTP\mtp-Qwen3.8-Flash-Next-shared-Q8_0.gguf'
$env:PATH = "$rocm\bin;$rocm\lib\llvm\bin;$env:PATH"
$env:HSA_OVERRIDE_GFX_VERSION = '11.5.1'

function Test-Cfg($ctx, $ub, $topk, $port) {
  Get-Process llama-server -ErrorAction SilentlyContinue | Stop-Process -Force
  Start-Sleep -Seconds 4
  $a = @('-m',$ud,'-dev','ROCm0','-ngl','999','-fa','on','-fit','off','--load-mode','none',
    '-ctk','f16','-ctv','f16','-c',"$ctx",'-b',"$ub",'-ub',"$ub",'--parallel','1','--jinja',
    '-md',$head,'--spec-type','draft-mtp','--spec-draft-n-max','2',
    '--override-kv',"qwen4exp.attention.indexer.top_k=int:$topk",
    '--host','127.0.0.1','--port',"$port",'--no-webui')
  $p = Start-Process -FilePath $bin -ArgumentList $a -PassThru -RedirectStandardError (Join-Path $res "ts-$ctx-$topk.err") -NoNewWindow
  $up=$false
  for($i=0;$i -lt 72;$i++){ if($p.HasExited){break}; try{ if((Invoke-WebRequest "http://127.0.0.1:$port/health" -TimeoutSec 3 -UseBasicParsing).StatusCode -eq 200){$up=$true;break} }catch{ Start-Sleep 5 } }
  if (-not $up) {
    $tail = ((Get-Content (Join-Path $res "ts-$ctx-$topk.err") -Tail 3) -join ' | ')
    Write-Output "ctx=$ctx top_k=$topk -> FAILED: $tail"
  } else {
    Write-Output "ctx=$ctx top_k=$topk -> LOADED"
    python "$root\indexer-test.py" $port "ctx$ctx-topk$topk" "1024,8192,16384" 2>&1 | Select-Object -Last 4
  }
  Get-Process llama-server -ErrorAction SilentlyContinue | Stop-Process -Force
  Start-Sleep -Seconds 2
}

# top_k just above ctx: dense draft, minimal indexer allocation
Test-Cfg 65536  8192 69632 8250
Test-Cfg 131072 8192 135168 8251
Write-Output "==== sweet-spot done ===="
