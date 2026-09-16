# headline-sweep.ps1 — find the largest ctx that works with ub 16384 + MTP at the 96 GB carve.
$ErrorActionPreference = 'Continue'
$bin  = 'C:\AI\build\strix-llama-win\build-win\bin\llama-server.exe'
$rocm = 'C:\Program Files\AMD\ROCm\7.2'
$root = 'C:\Projects\REV-N-ornith-eval-20260911\kernel-work'
$res  = Join-Path $root 'results'
$ud   = 'C:\AI\models\qwen38-flash\unsloth-UD-IQ4_XS\Qwen3.8-Flash-Next-UD-IQ4_XS-00001-of-00003.gguf'
$head = 'C:\AI\models\qwen38-flash\unsloth-UD-IQ4_XS\MTP\mtp-Qwen3.8-Flash-Next-shared-Q8_0.gguf'
$env:PATH = "$rocm\bin;$rocm\lib\llvm\bin;$env:PATH"
$env:HSA_OVERRIDE_GFX_VERSION = '11.5.1'

function Test-Cfg($ctx, $ub, $port) {
  Get-Process llama-server -ErrorAction SilentlyContinue | Stop-Process -Force
  Start-Sleep -Seconds 4
  $a = @('-m',$ud,'-dev','ROCm0','-ngl','999','-fa','on','-fit','off','--load-mode','none',
    '-ctk','f16','-ctv','f16','-c',"$ctx",'-b',"$ub",'-ub',"$ub",'--parallel','1','--jinja',
    '-md',$head,'--spec-type','draft-mtp','--spec-draft-n-max','2',
    '--override-kv','qwen4exp.attention.indexer.top_k=int:65536',
    '--host','127.0.0.1','--port',"$port",'--no-webui')
  $p = Start-Process -FilePath $bin -ArgumentList $a -PassThru -RedirectStandardError (Join-Path $res "hs-$ctx-$ub.err") -NoNewWindow
  $up=$false
  for($i=0;$i -lt 72;$i++){ if($p.HasExited){break}; try{ if((Invoke-WebRequest "http://127.0.0.1:$port/health" -TimeoutSec 3 -UseBasicParsing).StatusCode -eq 200){$up=$true;break} }catch{ Start-Sleep 5 } }
  if ($up) {
    Write-Output "ctx=$ctx ub=$ub -> LOADED"
  } else {
    $tail = (Get-Content (Join-Path $res "hs-$ctx-$ub.err") -Tail 3) -join ' | '
    Write-Output "ctx=$ctx ub=$ub -> FAILED: $tail"
  }
  Get-Process llama-server -ErrorAction SilentlyContinue | Stop-Process -Force
  Start-Sleep -Seconds 2
  return $up
}

Write-Output "=== ctx sweep at ub 16384 ==="
Test-Cfg 49152  16384 8240
Test-Cfg 98304  16384 8241
Test-Cfg 131072 16384 8242
Write-Output "=== ub sweep at ctx 131072 ==="
Test-Cfg 131072 8192  8243
Write-Output "=== done ==="
