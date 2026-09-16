# op-breakdown.ps1 — WHERE does the 80% verify time actually go?
# Runs the server with LLAMA_OP_TIMING=2 so per-op GPU times are measured in-graph.
# Answers: is the target forward pass spread across GEMMs (bad news, we cannot beat it),
# or dominated by a few ops we can attack?
param([int]$Prompt = 8192, [int]$Gen = 128, [int]$Ctx = 16384, [int]$Port = 8283)
$ErrorActionPreference = 'Continue'
$bin  = 'C:\AI\build\strix-llama-win\build-therock\bin\llama-server.exe'
$sdk  = 'C:\AI\sdk\therock1151'
$root = 'C:\Projects\REV-N-ornith-eval-20260911\kernel-work'
$res  = Join-Path $root 'results'
$model = 'C:\AI\models\qwen38-flash\projfix\Qwen3.8-Flash-Next-IQ4_NL-PROJFIX-00001-of-00009.gguf'
$head  = 'C:\AI\models\qwen38-flash\projfix\mtp-Qwen3.8-Flash-Next-shared-Q8_0.gguf'

Get-Process llama-server -ErrorAction SilentlyContinue | Stop-Process -Force
Start-Sleep -Seconds 4
$env:PATH = "$sdk\bin;$sdk\lib\llvm\bin;$env:PATH"
$env:ROCM_PATH = $sdk; $env:HIP_PATH = $sdk
$env:HIP_DEVICE_LIB_PATH = "$sdk\lib\llvm\amdgcn\bitcode"
$env:GGML_HIP_ENABLE_UNIFIED_MEMORY = '1'
$env:HSA_OVERRIDE_GFX_VERSION = '11.5.1'

# the whole point of this run
$env:LLAMA_OP_TIMING = '2'
$env:LLAMA_OP_TIMING_EVERY = '8'
# widen the op filter: catch everything that could plausibly be large
$env:LLAMA_OP_TIMING_OPS = 'mul_mat,mul_mat_id,ssm,gated_delta,flash_attn,get_rows,top_k,moe,softmax,rope,norm,rms_norm,cont,add,silu,cpy,scale,concat,pad,view,permute,transpose'

$a = @('-m',$model,'-md',$head,'-dev','ROCm0','-ngl','999','-fa','on','-fit','off','--load-mode','none',
  '-ctk','f16','-ctv','f16','-c',"$Ctx",'-b','2048','-ub','2048','--parallel','1',
  '--host','127.0.0.1','--port',"$Port",'--no-webui',
  '--spec-type','draft-mtp','--spec-draft-n-max','2')
$serr = Join-Path $res 'opb.err'; $sout = Join-Path $res 'opb.out'
Remove-Item $serr,$sout -ErrorAction SilentlyContinue
$p = Start-Process -FilePath $bin -ArgumentList $a -PassThru -RedirectStandardOutput $sout -RedirectStandardError $serr -NoNewWindow
$ok=$false; $t0=Get-Date
while (((Get-Date)-$t0).TotalSeconds -lt 900) {
  if ($p.HasExited) { "EXITED $($p.ExitCode)"; break }
  try { if ((Invoke-WebRequest "http://127.0.0.1:$Port/health" -TimeoutSec 5 -UseBasicParsing).StatusCode -eq 200) { $ok=$true; break } } catch { Start-Sleep -Seconds 5 }
}
if ($ok) {
  "READY $([int]((Get-Date)-$t0).TotalSeconds)s"
  # warm, then measure: the op summary prints every 8 replays
  python "$root\fnbench.py" --port $Port --label "opb-warm" --sizes "$Prompt" --gen 64 --repeats 1 --out (Join-Path $res 'opb-warm.json') 2>&1 | Out-Null
  python "$root\fnbench.py" --port $Port --label "opb" --sizes "$Prompt" --gen $Gen --repeats 1 --out (Join-Path $res 'opb.json') 2>&1 |
    Select-String -Pattern 'n=|decode'
}
Start-Sleep -Seconds 2
Get-Process llama-server -ErrorAction SilentlyContinue | Stop-Process -Force
Start-Sleep -Seconds 3

"=== OP_TIMING_IG summaries found ==="
$txt = ''
try { $txt = [IO.File]::ReadAllText($serr) } catch {}
$lines = ($txt -replace "`r",'') -split "`n"
$capture = $false; $count = 0
foreach ($l in $lines) {
  if ($l -match 'OP_TIMING_IG') { $capture = $true; $count++ }
  if ($capture) {
    if ($l.Trim()) { Write-Output ("  " + $l.TrimEnd()) }
    if ($l -match '^\s*$' -and $count -gt 0) { }
  }
}
"  (lines matched: $count)"
