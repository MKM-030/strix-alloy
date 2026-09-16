# dump-projfix-hidden.ps1 — Phase 1: dump PROJFIX trunk hidden states for draft-head training.
# Run the built llama-hidden-dump on the real target trunk (PROJFIX + shared MTP sidecar so the
# nextn block exists). Conservative token count; prints memory before/after so we can see the
# lazy-reader footprint.
param(
  [string]$Tag = "projfix-hd",
  [int]$NTokens = 16384, [int]$Window = 2048,
  [string]$Corpus = "C:\Projects\REV-N-ornith-eval-20260911\kernel-work\bench-corpus.txt"
)
$ErrorActionPreference = 'Continue'
$bin  = 'C:\AI\build\strix-llama-win\build-therock\bin\llama-hidden-dump.exe'
$sdk  = 'C:\AI\sdk\therock1151'
$root = 'C:\Projects\REV-N-ornith-eval-20260911\kernel-work'
$res  = Join-Path $root 'results'
$prefix = Join-Path $res $Tag
$log  = Join-Path $res "hd-$Tag.log"
function Log($m) { $m | Tee-Object -FilePath $log -Append }

$model = 'C:\AI\models\qwen38-flash\projfix\Qwen3.8-Flash-Next-IQ4_NL-PROJFIX-00001-of-00009.gguf'
$head  = 'C:\AI\models\qwen38-flash\projfix\mtp-Qwen3.8-Flash-Next-shared-Q8_0.gguf'

Get-Process llama-hidden-dump,llama-server -ErrorAction SilentlyContinue | ForEach-Object { Stop-Process -Id $_.Id -Force }
Start-Sleep -Seconds 2
$env:PATH = "$sdk\bin;$sdk\lib\llvm\bin;$env:PATH"
$env:ROCM_PATH = $sdk; $env:HIP_PATH = $sdk
$env:HIP_DEVICE_LIB_PATH = "$sdk\lib\llvm\amdgcn\bitcode"
$env:HSA_OVERRIDE_GFX_VERSION = '11.5.1'

Remove-Item "$prefix.tokens","$prefix.h","$prefix.json" -ErrorAction SilentlyContinue

# the trunk emits h_nextn itself (its last-layer hidden, as 4 HC streams) -- no MTP sidecar needed.
# `-md` is a server-only flag and common_params rejects it here.
$a = @('-m',$model,'-dev','ROCm0','-ngl','999','-fa','on','-fit','off','--load-mode','none',
  '-ctk','f16','-ctv','f16','-c',"$Window",'-b',"$Window",
  '-f',$Corpus,'--out',$prefix,'--ntokens',"$NTokens",'--window',"$Window")

$os = Get-CimInstance Win32_OperatingSystem
Log "==== $Tag $(Get-Date -Format o) ===="
Log ("argv: " + ($a -join ' '))
Log ("free before: {0:N1} GB" -f ($os.FreePhysicalMemory/1MB))

$t0 = Get-Date
& $bin @a 2>&1 | Tee-Object -FilePath $log -Append
$rc = $LASTEXITCODE
$os = Get-CimInstance Win32_OperatingSystem
Log ("exit=$rc  elapsed={0:N0}s  free after: {1:N1} GB" -f ((Get-Date)-$t0).TotalSeconds, ($os.FreePhysicalMemory/1MB))
Log "--- artifacts ---"
Get-ChildItem "$prefix*" -ErrorAction SilentlyContinue | ForEach-Object { Log ("  {0}  {1:N2} MB" -f $_.Name, ($_.Length/1MB)) }
Get-Content "$prefix.json" -ErrorAction SilentlyContinue | ForEach-Object { Log $_ }
Get-Process llama-hidden-dump,llama-server -ErrorAction SilentlyContinue | Stop-Process -Force
