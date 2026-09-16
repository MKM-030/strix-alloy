# phase2-cascade.ps1 — test the multi-drafter cascade: n-gram lookup ahead of MTP.
# The fork runs spec impls in fixed priority order; n-gram types are listed before DRAFT_* types,
# so enabling both means "cheap table lookup first, MTP as fallback".
param([string]$Tag = "p2-cascade", [string]$SpecTypes = "ngram-simple,draft-mtp",
      [string]$Sizes = "1024,8192,16384", [int]$Gen = 256, [int]$Repeats = 3, [string]$Extra = "")
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

Get-Process llama-server -ErrorAction SilentlyContinue | ForEach-Object { Stop-Process -Id $_.Id -Force }
Start-Sleep -Seconds 4
$a = @('-m',$mdl,'-dev','ROCm0','-ngl','999','-fa','on','-fit','off','--load-mode','none',
  '-ctk','f16','-ctv','f16','-c','32768','-b','2048','-ub','2048','--parallel','1',
  '--host','127.0.0.1','--port','8290','--no-webui',
  '-md',$head,'--spec-draft-n-max','4')
foreach ($t in $SpecTypes.Split(',')) { $a += @('--spec-type', $t) }
if ($Extra -ne "") { $a += ($Extra -split '\s+') }
Write-Output "==== $Tag  specs=$SpecTypes ===="
$p = Start-Process -FilePath $bin -ArgumentList $a -PassThru -RedirectStandardError (Join-Path $res "$Tag.err") -NoNewWindow
$up=$false
for($i=0;$i -lt 60;$i++){ if($p.HasExited){break}; try{ if((Invoke-WebRequest 'http://127.0.0.1:8290/health' -TimeoutSec 3 -UseBasicParsing).StatusCode -eq 200){$up=$true;break} }catch{ Start-Sleep 5 } }
if (-not $up) {
  Write-Output "  FAILED:"; Get-Content (Join-Path $res "$Tag.err") -Tail 4
} else {
  python "$root\indexer-test.py" 8290 $Tag $Sizes 2>&1 | Select-Object -Last 5
  Select-String -Path (Join-Path $res "$Tag.err") -Pattern 'draft acceptance|ngram|lookup' | Select-Object -Last 4 |
    ForEach-Object { Write-Output ("  " + $_.Line.Trim()) }
}
Get-Process llama-server -ErrorAction SilentlyContinue | Stop-Process -Force
Write-Output "==== done ===="
