# headline.ps1 — the config the 96 GB carve unlocks: PROJFIX + MTP + top_k fix + ub16384 + deep ctx.
$ErrorActionPreference = 'Continue'
$bin  = 'C:\AI\build\strix-llama-win\build-win\bin\llama-server.exe'
$rocm = 'C:\Program Files\AMD\ROCm\7.2'
$root = 'C:\Projects\REV-N-ornith-eval-20260911\kernel-work'
$res  = Join-Path $root 'results'
$proj = '\\wsl.localhost\Ubuntu-24.04\home\revn\models\flash-next-strix\Qwen3.8-Flash-Next-IQ4_NL-PROJFIX-00001-of-00009.gguf'
$ud   = 'C:\AI\models\qwen38-flash\unsloth-UD-IQ4_XS\Qwen3.8-Flash-Next-UD-IQ4_XS-00001-of-00003.gguf'
$head = 'C:\AI\models\qwen38-flash\unsloth-UD-IQ4_XS\MTP\mtp-Qwen3.8-Flash-Next-shared-Q8_0.gguf'
$env:PATH = "$rocm\bin;$rocm\lib\llvm\bin;$env:PATH"
$env:HSA_OVERRIDE_GFX_VERSION = '11.5.1'

Get-Process llama-server -ErrorAction SilentlyContinue | Stop-Process -Force
Start-Sleep -Seconds 4
Write-Output "==== headline: UD + MTP + top_k fix, ub 16384, ctx 262144 (only possible at 96 GB carve) ===="
$a = @('-m',$ud,'-dev','ROCm0','-ngl','999','-fa','on','-fit','off','--load-mode','none',
  '-ctk','f16','-ctv','f16','-c','262144','-b','16384','-ub','16384','--parallel','1','--jinja',
  '-md',$head,'--spec-type','draft-mtp','--spec-draft-n-max','2',
  '--override-kv','qwen4exp.attention.indexer.top_k=int:65536',
  '--host','127.0.0.1','--port','8230','--no-webui')
$p = Start-Process -FilePath $bin -ArgumentList $a -PassThru -RedirectStandardError (Join-Path $res "hl.err") -NoNewWindow
$up=$false
for($i=0;$i -lt 90;$i++){ if($p.HasExited){break}; try{ if((Invoke-WebRequest 'http://127.0.0.1:8230/health' -TimeoutSec 3 -UseBasicParsing).StatusCode -eq 200){$up=$true;break} }catch{ Start-Sleep 5 } }
if (-not $up) {
  Write-Output "FAILED TO START (or died):"
  Get-Content (Join-Path $res "hl.err") -Tail 6
} else {
  Write-Output "loaded OK at 262k ctx + ub16384"
  python "$root\indexer-test.py" 8230 "headline-ud-ub16k-262k" "1024,8192,16384,32768" 2>&1 | Select-Object -Last 6
}
Get-Process llama-server -ErrorAction SilentlyContinue | Stop-Process -Force
Write-Output "==== headline done ===="
