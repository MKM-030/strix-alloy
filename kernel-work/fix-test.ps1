# fix-test.ps1 — test the source fix: default top_k (target keeps sparse QSA) + MTP at depth.
param([int]$Ctx = 131072, [int]$Ub = 8192, [string]$Depths = "1024,8192,32768")
$ErrorActionPreference = 'Continue'
$bin  = 'C:\AI\build\strix-llama-win\build-win\bin\llama-server.exe'
$rocm = 'C:\Program Files\AMD\ROCm\7.2'
$root = 'C:\Projects\REV-N-ornith-eval-20260911\kernel-work'
$res  = Join-Path $root 'results'
$ud   = 'C:\AI\models\qwen38-flash\unsloth-UD-IQ4_XS\Qwen3.8-Flash-Next-UD-IQ4-IQ4_XS-00001-of-00003.gguf'
$ud   = 'C:\AI\models\qwen38-flash\unsloth-UD-IQ4_XS\Qwen3.8-Flash-Next-UD-IQ4_XS-00001-of-00003.gguf'
$head = 'C:\AI\models\qwen38-flash\unsloth-UD-IQ4_XS\MTP\mtp-Qwen3.8-Flash-Next-shared-Q8_0.gguf'
$env:PATH = "$rocm\bin;$rocm\lib\llvm\bin;$env:PATH"
$env:HSA_OVERRIDE_GFX_VERSION = '11.5.1'

Get-Process llama-server -ErrorAction SilentlyContinue | Stop-Process -Force
Start-Sleep -Seconds 4
Write-Output "==== fix test: DEFAULT top_k (no override) + MTP, ctx=$Ctx ub=$Ub ===="
$a = @('-m',$ud,'-dev','ROCm0','-ngl','999','-fa','on','-fit','off','--load-mode','none',
  '-ctk','f16','-ctv','f16','-c',"$Ctx",'-b',"$Ub",'-ub',"$Ub",'--parallel','1','--jinja',
  '-md',$head,'--spec-type','draft-mtp','--spec-draft-n-max','2',
  '--host','127.0.0.1','--port','8260','--no-webui')
$p = Start-Process -FilePath $bin -ArgumentList $a -PassThru -RedirectStandardError (Join-Path $res "fx.err") -NoNewWindow
$up=$false
for($i=0;$i -lt 90;$i++){ if($p.HasExited){break}; try{ if((Invoke-WebRequest 'http://127.0.0.1:8260/health' -TimeoutSec 3 -UseBasicParsing).StatusCode -eq 200){$up=$true;break} }catch{ Start-Sleep 5 } }
if (-not $up) {
  Write-Output "FAILED:"; Get-Content (Join-Path $res "fx.err") -Tail 5
} else {
  Write-Output "LOADED (target sparse + draft dense)"
  python "$root\indexer-test.py" 8260 "FIX-default-topk-ctx$Ctx" "$Depths" 2>&1 | Select-Object -Last 6
}
Get-Process llama-server -ErrorAction SilentlyContinue | Stop-Process -Force
Write-Output "==== fix test done ===="
