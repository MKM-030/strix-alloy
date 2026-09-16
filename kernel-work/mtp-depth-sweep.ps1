# mtp-depth-sweep.ps1 — sweep MTP draft depth; measure decode at several depths.
# ub 2048 (Bug A requires it with -md). ctx 32768 so we can test to 16k.
param([string]$Depths = "1,2,3,4,6", [string]$Sizes = "1024,8192,16384", [int]$Gen = 256)
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
$env:GGML_HIP_ENABLE_UNIFIED_MEMORY = '1'
$env:HSA_OVERRIDE_GFX_VERSION = '11.5.1'

foreach ($n in $Depths.Split(',')) {
  $tag = "mtp-d$n"
  Write-Output "==== $tag (spec-draft-n-max=$n) ===="
  Get-Process llama-server -ErrorAction SilentlyContinue | Stop-Process -Force
  Start-Sleep -Seconds 4
  $a = @('-m',$mdl,'-dev','ROCm0','-ngl','999','-fa','on','-fit','off','--load-mode','none',
    '-ctk','f16','-ctv','f16','-c','32768','-b','2048','-ub','2048','--parallel','1',
    '-md',$head,'--spec-type','draft-mtp','--spec-draft-n-max',"$n",
    '--host','127.0.0.1','--port','8280','--no-webui')
  $p = Start-Process -FilePath $bin -ArgumentList $a -PassThru -RedirectStandardError (Join-Path $res "md-$tag.err") -NoNewWindow
  $up=$false
  for($i=0;$i -lt 60;$i++){ if($p.HasExited){break}; try{ if((Invoke-WebRequest 'http://127.0.0.1:8280/health' -TimeoutSec 3 -UseBasicParsing).StatusCode -eq 200){$up=$true;break} }catch{ Start-Sleep 5 } }
  if (-not $up) { Write-Output "  FAILED: $((Get-Content (Join-Path $res "md-$tag.err") -Tail 2) -join ' | ')"; continue }
  python "$root\indexer-test.py" 8280 $tag $Sizes 2>&1 | Select-Object -Last 5
  # report acceptance from the server log
  $acc = Select-String -Path (Join-Path $res "md-$tag.err") -Pattern 'draft acceptance' | Select-Object -Last 1
  if ($acc) { Write-Output ("  " + ($acc.Line -replace '.*draft acceptance','draft acceptance').Trim()) }
  Get-Process llama-server -ErrorAction SilentlyContinue | Stop-Process -Force
  Start-Sleep -Seconds 2
}
Write-Output "==== depth sweep done ===="
