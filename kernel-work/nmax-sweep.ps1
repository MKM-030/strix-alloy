# nmax-sweep.ps1 — proper n-max sweep on the CORRECTED 96 GB carve (the earlier one was invalidated
# by the degraded carve). Same model/quant/head/ub; vary only --spec-draft-n-max.
param([string]$Depths = "1,2,3,4,6,8", [string]$Sizes = "1024,8192,16384", [int]$Gen = 256)
$ErrorActionPreference = 'Continue'
$bin  = 'C:\AI\build\strix-llama-win\build-therock\bin\llama-server.exe'
$sdk  = 'C:\AI\sdk\therock1151'
$root = 'C:\Projects\REV-N-ornith-eval-20260911\kernel-work'
$res  = Join-Path $root 'results'
$mdl  = 'C:\AI\models\qwen38-flash\projfix\Qwen3.8-Flash-Next-IQ4_NL-PROJFIX-00001-of-00009.gguf'
$head = 'C:\AI\models\qwen38-flash\projfix\mtp-Qwen3.8-Flash-Next-shared-Q8_0.gguf'
$env:PATH = "$sdk\bin;$sdk\lib\llvm\bin;$env:PATH"
$env:ROCM_PATH = $sdk; $env:HIP_PATH = $sdk
$env:HIP_DEVICE_LIB_PATH = "$sdk\lib\llvm\amdgcn\bitcode"
$env:HSA_OVERRIDE_GFX_VERSION = '11.5.1'

foreach ($n in $Depths.Split(',')) {
  $tag = "nmax-$n"
  Write-Output "==== n-max=$n ===="
  Get-Process llama-server -ErrorAction SilentlyContinue | ForEach-Object { Stop-Process -Id $_.Id -Force }
  Start-Sleep -Seconds 4
  $a = @('-m',$mdl,'-dev','ROCm0','-ngl','999','-fa','on','-fit','off','--load-mode','none',
    '-ctk','f16','-ctv','f16','-c','32768','-b','2048','-ub','2048','--parallel','1',
    '-md',$head,'--spec-type','draft-mtp','--spec-draft-n-max',"$n",
    '--host','127.0.0.1','--port','8300','--no-webui')
  $p = Start-Process -FilePath $bin -ArgumentList $a -PassThru -RedirectStandardError (Join-Path $res "$tag.err") -NoNewWindow
  $up=$false
  for($i=0;$i -lt 60;$i++){ if($p.HasExited){break}; try{ if((Invoke-WebRequest 'http://127.0.0.1:8300/health' -TimeoutSec 3 -UseBasicParsing).StatusCode -eq 200){$up=$true;break} }catch{ Start-Sleep 5 } }
  if (-not $up) { Write-Output "  FAILED: $((Get-Content (Join-Path $res "$tag.err") -Tail 2) -join ' | ')"; continue }
  python "$root\indexer-test.py" 8300 $tag $Sizes 2>&1 | Select-Object -Last 5
  Get-Process llama-server -ErrorAction SilentlyContinue | Stop-Process -Force
  Start-Sleep -Seconds 2
}
Write-Output "==== nmax sweep done ===="
