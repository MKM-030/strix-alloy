#requires -Version 5.1
# reproduce-b1-shared-mtp-fit.ps1 — replay the shared-MTP / large-ubatch load failure.
#
# Claim under test (docs/shared-mtp-fit-rootcause-20260915.md): with the shared MTP sidecar and
# --fit ON, the auto-fit preflight tries to measure the sidecar standalone, fails because the
# sidecar omits token_embd/output_norm, degrades to "fitting without it", and the draft context
# gets no memory allowance -> a large -ub under-reserves device memory -> load failure.
#
# We capture, per ubatch:
#   - whether the server reaches /health
#   - the "failed to measure the memory of the extra model, fitting without it" line
#   - any allocation/OOM/assert error and the exit code
# The -fit off runs are the control: they should always reach /health (our production config).
param([int]$Ctx = 32768, [int]$Port = 8302)
$ErrorActionPreference = 'Continue'
$bin  = 'C:\AI\build\strix-llama-win\build-therock\bin\llama-server.exe'
$sdk  = 'C:\AI\sdk\therock1151'
$root = 'C:\Projects\REV-N-ornith-eval-20260911\kernel-work'
$res  = Join-Path $root 'results'
$model = 'C:\AI\models\qwen38-flash\projfix\Qwen3.8-Flash-Next-IQ4_NL-PROJFIX-00001-of-00009.gguf'
$head  = 'C:\AI\models\qwen38-flash\projfix\mtp-Qwen3.8-Flash-Next-shared-Q8_0.gguf'

$env:PATH = "$sdk\bin;$sdk\lib\llvm\bin;$env:PATH"
$env:ROCM_PATH = $sdk; $env:HIP_PATH = $sdk
$env:HIP_DEVICE_LIB_PATH = "$sdk\lib\llvm\amdgcn\bitcode"
$env:GGML_HIP_ENABLE_UNIFIED_MEMORY = '1'
$env:HSA_OVERRIDE_GFX_VERSION = '11.5.1'

function Try-Config([string]$tag, [string]$fit, [int]$ub, [int]$b) {
  Get-Process llama-server -ErrorAction SilentlyContinue | Stop-Process -Force
  Start-Sleep -Seconds 5
  $a = @('-m',$model,'-md',$head,'-dev','ROCm0','-ngl','999','--n-gpu-layers-draft','999',
    '-fa','on','--spec-type','draft-mtp','--spec-draft-n-max','2','--spec-draft-p-min','0.0',
    '--load-mode','none','-ctk','f16','-ctv','f16','-c',"$Ctx",'-b',"$b",'-ub',"$ub",
    '--parallel','1','--host','127.0.0.1','--port',"$Port",'--no-webui','--seed','1234')
  if ($fit -eq 'on') { $a += @('-fit','on') } else { $a += @('-fit','off') }
  $serr = Join-Path $res "b1-$tag.err"; $sout = Join-Path $res "b1-$tag.out"
  Remove-Item $serr,$sout -ErrorAction SilentlyContinue
  $p = Start-Process -FilePath $bin -ArgumentList $a -PassThru -RedirectStandardOutput $sout -RedirectStandardError $serr -NoNewWindow
  $ok=$false; $t0=Get-Date
  while (((Get-Date)-$t0).TotalSeconds -lt 420) {
    if ($p.HasExited) { break }
    try { if ((Invoke-WebRequest "http://127.0.0.1:$Port/health" -TimeoutSec 5 -UseBasicParsing).StatusCode -eq 200) { $ok=$true; break } } catch { Start-Sleep -Seconds 4 }
  }
  $elapsed=[int]((Get-Date)-$t0).TotalSeconds
  $exit = if ($p.HasExited) { $p.ExitCode } else { $null }
  $txt = ''
  foreach ($f in @($serr,$sout)) { if (Test-Path $f) { $txt += (Get-Content $f -Raw -ErrorAction SilentlyContinue) } }
  $fitWarn = ($txt -match 'failed to measure the memory of the extra model')
  $oom     = ($txt -match 'out of memory|failed to allocate|GGML_ASSERT|hipErrorOutOfMemory|failed to load model|ggml_backend_alloc')
  # keep only the interesting lines
  $keep = ($txt -split "`n") | Where-Object { $_ -match 'extra model|fit|out of memory|failed to alloc|GGML_ASSERT|n_ctx|n_ubatch|n_batch|error|Error' } | Select-Object -First 25
  Write-Output ("[$tag] fit=$fit ub=$ub b=$b -> ready=$ok exit=$exit t=${elapsed}s fitWarn=$fitWarn oomMarker=$oom")
  foreach ($l in $keep) { Write-Output ("      | " + $l.Trim()) }
  Start-Sleep -Seconds 2
  Get-Process llama-server -ErrorAction SilentlyContinue | Stop-Process -Force
  Start-Sleep -Seconds 3
  return [pscustomobject]@{ tag=$tag; fit=$fit; ub=$ub; b=$b; ready=$ok; exit=$exit; fit_warn=$fitWarn; oom_marker=$oom }
}

$rows = @()
# control (our production config): fit off should always load
$rows += Try-Config 'fitoff-ub2048' 'off' 2048 2048
# under test: fit on, large ubatch
$rows += Try-Config 'fiton-ub2048'  'on'  2048 2048
$rows += Try-Config 'fiton-ub8192'  'on'  8192 8192
$rows += Try-Config 'fiton-ub16384' 'on'  16384 16384
$rows | ConvertTo-Json -Depth 4 | Set-Content (Join-Path $res 'b1-repro.json')
Write-Output 'done'
