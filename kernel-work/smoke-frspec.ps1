# smoke-frspec.ps1 — decisive test: does the FIXED FR-Spec 65k head (d2t corrected) load and run?
# Replays the exact config that previously faulted at graph warmup (tr-p3-frspec3), but at a small
# ctx so the smoke test is cheap. The old fault happened during model-init warmup, before any decode,
# so ctx size does not affect whether the fault reproduces.
param(
  [string]$Tag = "smoke-frspec-fixed",
  [int]$Ctx = 8192, [int]$B = 2048, [int]$Ub = 2048,
  [int]$Gen = 32, [int]$Port = 8271, [string]$ExtraArgs = ""
)
$ErrorActionPreference = 'Continue'
$bin  = 'C:\AI\build\strix-llama-win\build-therock\bin\llama-server.exe'
$sdk  = 'C:\AI\sdk\therock1151'
$root = 'C:\Projects\REV-N-ornith-eval-20260911\kernel-work'
$res  = Join-Path $root 'results'
New-Item -ItemType Directory -Force -Path $res | Out-Null

$model = 'C:\AI\models\qwen38-flash\projfix\Qwen3.8-Flash-Next-IQ4_NL-PROJFIX-00001-of-00009.gguf'
$mtp   = 'C:\AI\models\qwen38-flash\projfix\mtp-frspec-65k-pwhead.gguf'

Get-Process llama-server -ErrorAction SilentlyContinue | ForEach-Object { Stop-Process -Id $_.Id -Force }
Start-Sleep -Seconds 3
$env:PATH = "$sdk\bin;$sdk\lib\llvm\bin;$env:PATH"
$env:ROCM_PATH = $sdk; $env:HIP_PATH = $sdk
$env:HIP_DEVICE_LIB_PATH = "$sdk\lib\llvm\amdgcn\bitcode"
$env:GGML_HIP_ENABLE_UNIFIED_MEMORY = '1'
$env:HSA_OVERRIDE_GFX_VERSION = '11.5.1'

$a = @('-m',$model,'-dev','ROCm0','-ngl','999','-fa','on','-fit','off','--load-mode','none',
  '--lazy-mode','on-direct','-ctk','f16','-ctv','f16','-c',"$Ctx",'-b',"$B",'-ub',"$Ub",
  '--parallel','1','--host','127.0.0.1','--port',"$Port",'--no-webui',
  '-md',$mtp,'--spec-type','draft-mtp','--spec-draft-n-max','2')
if ($ExtraArgs -ne "") { $a += $ExtraArgs.Split(' ') }

$sout = Join-Path $res "sm-$Tag.out"; $serr = Join-Path $res "sm-$Tag.err"; $blog = Join-Path $res "smb-$Tag.log"
function Note($m) { $m | Out-File -FilePath $blog -Append -Encoding utf8 }
Note "==== $Tag $(Get-Date -Format o) ===="
Note "argv: $($a -join ' ')"
$p = Start-Process -FilePath $bin -ArgumentList $a -PassThru -RedirectStandardOutput $sout -RedirectStandardError $serr -NoNewWindow
Note "pid=$($p.Id)"
$ok=$false; $t0=Get-Date
while (((Get-Date)-$t0).TotalSeconds -lt 900) {
  if ($p.HasExited) { Note "EXITED code=$($p.ExitCode)"; Get-Content $serr -Tail 15; break }
  try { if ((Invoke-WebRequest "http://127.0.0.1:$Port/health" -TimeoutSec 5 -UseBasicParsing).StatusCode -eq 200) { $ok=$true; break } } catch { Start-Sleep -Seconds 5 }
}
if ($ok) {
  Note ("READY after " + [int]((Get-Date)-$t0).TotalSeconds + "s")
  python "$root\fnbench.py" --port $Port --label $Tag --sizes "1024" --gen $Gen --repeats 1 `
    --out (Join-Path $res "$Tag.json") 2>&1 | Tee-Object -FilePath $blog -Append
} else {
  Note "NOT READY"
}
Note "--- spec/d2t evidence from log ---"
Select-String -Path $serr -Pattern 'd2t|t2d|draft-vocab|nextn|spec_draft|n_draft|accepted' -ErrorAction SilentlyContinue |
  ForEach-Object { Note $_.Line }
Stop-Process -Id $p.Id -Force -ErrorAction SilentlyContinue
Start-Sleep -Seconds 3
Get-Process llama-server -ErrorAction SilentlyContinue | Stop-Process -Force
Note "done"
