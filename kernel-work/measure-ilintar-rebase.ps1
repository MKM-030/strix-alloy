# measure-ilintar-rebase.ps1 — prefill/decode ladder with ilintar's latest kernels (env gates removed).
# No LLAMA_* env vars: 40a9f4d0/ac1ebb4e0 compiled the tuned defaults in, so the launcher is plain.
param(
  [int]$Ctx = 65536, [int]$B = 16384, [int]$Ub = 16384,
  [string]$Sizes = "1024,8192,16384,32768", [int]$Gen = 128, [int]$Repeats = 3, [int]$Port = 8275
)
$ErrorActionPreference = 'Continue'
$bin  = 'C:\AI\build\strix-llama-win\build-therock\bin\llama-server.exe'
$sdk  = 'C:\AI\sdk\therock1151'
$root = 'C:\Projects\REV-N-ornith-eval-20260911\kernel-work'
$res  = Join-Path $root 'results'
$model = 'C:\AI\models\qwen38-flash\projfix\Qwen3.8-Flash-Next-IQ4_NL-PROJFIX-00001-of-00009.gguf'
$head  = 'C:\AI\models\qwen38-flash\projfix\mtp-Qwen3.8-Flash-Next-shared-Q8_0.gguf'
$blog  = Join-Path $res 'ilintar-rebase.log'

Get-Process llama-server -ErrorAction SilentlyContinue | Stop-Process -Force
Start-Sleep -Seconds 3
$env:PATH = "$sdk\bin;$sdk\lib\llvm\bin;$env:PATH"
$env:ROCM_PATH = $sdk; $env:HIP_PATH = $sdk
$env:HIP_DEVICE_LIB_PATH = "$sdk\lib\llvm\amdgcn\bitcode"
$env:GGML_HIP_ENABLE_UNIFIED_MEMORY = '1'
$env:HSA_OVERRIDE_GFX_VERSION = '11.5.1'

function Run($tag, $mtp, $nmax) {
  Get-Process llama-server -ErrorAction SilentlyContinue | Stop-Process -Force
  Start-Sleep -Seconds 4
  $a = @('-m',$model,'-dev','ROCm0','-ngl','999','-fa','on','-fit','off','--load-mode','none',
    '-ctk','f16','-ctv','f16','-c',"$Ctx",'-b',"$B",'-ub',"$Ub",'--parallel','1',
    '--host','127.0.0.1','--port',"$Port",'--no-webui')
  if ($mtp -ne "") { $a += @('-md',$mtp,'--spec-type','draft-mtp','--spec-draft-n-max',"$nmax") }
  $sout = Join-Path $res "ir-$tag.out"; $serr = Join-Path $res "ir-$tag.err"
  "==== $tag (mtp=$mtp nmax=$nmax) $(Get-Date -Format o) ====" | Out-File $blog -Append -Encoding utf8
  $p = Start-Process -FilePath $bin -ArgumentList $a -PassThru -RedirectStandardOutput $sout -RedirectStandardError $serr -NoNewWindow
  $ok=$false; $t0=Get-Date
  while (((Get-Date)-$t0).TotalSeconds -lt 900) {
    if ($p.HasExited) { "  EXITED code=$($p.ExitCode)" | Out-File $blog -Append -Encoding utf8; return }
    try { if ((Invoke-WebRequest "http://127.0.0.1:$Port/health" -TimeoutSec 5 -UseBasicParsing).StatusCode -eq 200) { $ok=$true; break } } catch { Start-Sleep -Seconds 5 }
  }
  if (-not $ok) { "  NOT READY" | Out-File $blog -Append -Encoding utf8; return }
  "  READY $([int]((Get-Date)-$t0).TotalSeconds)s" | Out-File $blog -Append -Encoding utf8
  python "$root\fnbench.py" --port $Port --label $tag --sizes $Sizes --gen $Gen --repeats $Repeats `
    --out (Join-Path $res "$tag.json") 2>&1 | Tee-Object -FilePath $blog -Append
  Get-Process llama-server -ErrorAction SilentlyContinue | Stop-Process -Force
}

# prefill shape (ub 16384, no drafter) and decode shape (ub 2048 + MTP) -- the two operating points
Run "il-prefill-ub16k" "" 0
Run "il-mtp-n2" $head 2
Get-Process llama-server -ErrorAction SilentlyContinue | Stop-Process -Force
"ALL DONE $(Get-Date -Format o)" | Out-File $blog -Append -Encoding utf8
