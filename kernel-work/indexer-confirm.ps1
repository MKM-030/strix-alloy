# indexer-confirm.ps1 — confirm the dense-draft workaround at increasing depth.
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

Get-Process llama-server -ErrorAction SilentlyContinue | Stop-Process -Force
Start-Sleep -Seconds 4
$a = @('-m',$mdl,'-dev','ROCm0','-ngl','999','-fa','on','-fit','off','--load-mode','none',
  '-ctk','f16','-ctv','f16','-c','32768','-b','2048','-ub','2048','--parallel','1','--jinja',
  '-md',$head,'--spec-type','draft-mtp','--spec-draft-n-max','2',
  '--override-kv','qwen4exp.attention.indexer.top_k=int:65536',
  '--host','127.0.0.1','--port','8220','--no-webui')
$p = Start-Process -FilePath $bin -ArgumentList $a -PassThru -RedirectStandardError (Join-Path $res "ic-dense-ok.err") -NoNewWindow
$up=$false
for($i=0;$i -lt 60;$i++){ if($p.HasExited){break}; try{ if((Invoke-WebRequest 'http://127.0.0.1:8220/health' -TimeoutSec 3 -UseBasicParsing).StatusCode -eq 200){$up=$true;break} }catch{ Start-Sleep 5 } }
if (-not $up) {
  Write-Output "FAILED TO START"
  Get-Content (Join-Path $res "ic-dense-ok.err") -Tail 4
} else {
  python "$root\indexer-test.py" 8220 "dense-draft topk=65536" "1024,2048,4096,8192,16384" 2>&1 | Select-Object -Last 7
}
Get-Process llama-server -ErrorAction SilentlyContinue | Stop-Process -Force
Write-Output "==== confirm done ===="
