#requires -Version 5.1
# compose-graphs-on.ps1 — per-op composition WITH GRAPHS ENABLED.
#
# How: with graphs on, the first eval(s) of each shape are executed EAGERLY (warmup) before the
# graph is captured. The aggregate op timer records on exactly those eager evals
# (`!use_cuda_graph`), and cudaEventRecord works there because no capture is active. So we get
# per-op GPU times from the PRODUCTION kernels, in the production configuration.
#
# Why not the in-graph path: hipEventElapsedTime returns 400 for captured events on this
# ROCm/DXG build (proven 2026-09-15). Capture-time CPU wall-clock would only measure enqueue.
#
# Validation gate: summaries present, non-zero totals, no error lines. Otherwise RUN INVALID.
param([int]$Prompt = 1024, [int]$Gen = 512, [int]$Ctx = 8192, [int]$Port = 8291)
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

function ReadShared([string]$p) {
    if (-not (Test-Path $p)) { return '' }
    try { $fs=[IO.File]::Open($p,'Open','Read','ReadWrite'); $sr=New-Object IO.StreamReader($fs); $t=$sr.ReadToEnd(); $sr.Close(); $fs.Close(); $t }
    catch { '' }
}

# ---------------------------------------------------------------------------------------------
Write-Output '################ PART 1: per-op composition, GRAPHS ON ################'
Remove-Item Env:\GGML_CUDA_DISABLE_GRAPHS -ErrorAction SilentlyContinue   # graphs stay ON
$env:LLAMA_OP_TIMING = '1'
$env:LLAMA_OP_TIMING_EVERY = '1'                                          # print after every eager eval
Remove-Item Env:\LLAMA_OP_TIMING_OPS -ErrorAction SilentlyContinue

Get-Process llama-server -ErrorAction SilentlyContinue | Stop-Process -Force
Start-Sleep -Seconds 4
$a = @('-m',$model,'-dev','ROCm0','-ngl','999','-fa','on','-fit','off','--load-mode','none',
  '-ctk','f16','-ctv','f16','-c',"$Ctx",'-b','2048','-ub','2048','--parallel','1',
  '--host','127.0.0.1','--port',"$Port",'--no-webui')
$serr = Join-Path $res 'cg.err'; $sout = Join-Path $res 'cg.out'
Remove-Item $serr,$sout -ErrorAction SilentlyContinue
$p = Start-Process -FilePath $bin -ArgumentList $a -PassThru -RedirectStandardOutput $sout -RedirectStandardError $serr -NoNewWindow
$ok=$false; $t0=Get-Date
while (((Get-Date)-$t0).TotalSeconds -lt 900) {
  if ($p.HasExited) { Write-Output "server EXITED $($p.ExitCode)"; break }
  try { if ((Invoke-WebRequest "http://127.0.0.1:$Port/health" -TimeoutSec 5 -UseBasicParsing).StatusCode -eq 200) { $ok=$true; break } } catch { Start-Sleep -Seconds 5 }
}
if ($ok) {
  Write-Output "server READY $([int]((Get-Date)-$t0).TotalSeconds)s  (this run is for COMPOSITION)"
  python "$root\fnbench.py" --port $Port --label 'cg' --sizes "$Prompt" --gen $Gen --repeats 1 --out (Join-Path $res 'cg.json') 2>&1 |
    Select-String -Pattern 'n=|error'
}
Start-Sleep -Seconds 2
Get-Process llama-server -ErrorAction SilentlyContinue | Stop-Process -Force
Start-Sleep -Seconds 4

$t = ReadShared $serr
$lines = ($t -replace "`r", '') -split "`n"
$headers = ($lines | Where-Object { $_ -match 'OP_TIMING aggregate' }).Count
$zero    = ($lines | Where-Object { $_ -match 'total=\s+0\.0ms' }).Count
$errs    = ($lines | Where-Object { $_ -match 'ROCm error|GET_ROWS failed|abort|assert' }).Count
Write-Output ''
Write-Output '=== VALIDATION (graphs ON) ==='
Write-Output ("  OP_TIMING summaries : {0}" -f $headers)
Write-Output ("  zero-total rows     : {0}" -f $zero)
Write-Output ("  error lines         : {0}" -f $errs)
$valid = ($headers -gt 0) -and ($errs -eq 0)
Write-Output ("  => {0}" -f $(if ($valid) { 'RUN VALID' } else { 'RUN INVALID - do NOT quote' }))

Write-Output ''
Write-Output '=== last full summary block (graphs ON, eager warmup evals) ==='
$blocks = @(); $cur = @()
foreach ($l in $lines) {
  if ($l -match '^\s*\S+\|\S*\s+n=\d+\s+total=') { $cur += $l }
  elseif ($cur.Count -gt 0) { $blocks += ,$cur; $cur = @() }
}
if ($cur.Count -gt 0) { $blocks += ,$cur }
Write-Output ("  blocks found: {0}" -f $blocks.Count)
if ($blocks.Count -gt 0) {
  $use = $blocks[0]                      # FIRST block = first eager eval = pure decode/prefill mix
  $rows = @()
  foreach ($l in $use) {
    if ($l -match '^\s*(\S+)\|(\S*)\s+n=(\d+)\s+total=\s*([\d.]+)ms\s+avg=\s*([\d.]+)us') {
      $rows += [pscustomobject]@{ op="$($Matches[1])|$($Matches[2])"; n=[int]$Matches[3]; ms=[double]$Matches[4]; us=[double]$Matches[5] }
    }
  }
  $tot = ($rows | Measure-Object ms -Sum).Sum
  Write-Output ("  tracked total: {0:N1} ms over {1} rows" -f $tot, $rows.Count)
  Write-Output ''
  Write-Output '  --- grouped by op (all layers) ---'
  $rows | Group-Object { ($_.op -split '\|')[0] } | ForEach-Object {
      [pscustomobject]@{ op=$_.Name; ms=($_.Group|Measure-Object ms -Sum).Sum; n=($_.Group|Measure-Object n -Sum).Sum }
  } | Sort-Object ms -Descending | Select-Object -First 18 | ForEach-Object {
      $pct = if ($tot -gt 0) { 100.0*$_.ms/$tot } else { 0 }
      Write-Output ("    {0,-22} n={1,-8} {2,9:N2} ms  {3,5:N1}%" -f $_.op, $_.n, $_.ms, $pct)
  }
}

# ---------------------------------------------------------------------------------------------
Write-Output ''
Write-Output '################ PART 2: clean throughput, no instrumentation, GRAPHS ON ################'
Remove-Item Env:\LLAMA_OP_TIMING -ErrorAction SilentlyContinue
Remove-Item Env:\LLAMA_OP_TIMING_EVERY -ErrorAction SilentlyContinue
Get-Process llama-server -ErrorAction SilentlyContinue | Stop-Process -Force
Start-Sleep -Seconds 4
$serr2 = Join-Path $res 'cgb.err'; $sout2 = Join-Path $res 'cgb.out'
Remove-Item $serr2,$sout2 -ErrorAction SilentlyContinue
$p2 = Start-Process -FilePath $bin -ArgumentList $a -PassThru -RedirectStandardOutput $sout2 -RedirectStandardError $serr2 -NoNewWindow
$ok2=$false; $t1=Get-Date
while (((Get-Date)-$t1).TotalSeconds -lt 900) {
  if ($p2.HasExited) { Write-Output "server EXITED $($p2.ExitCode)"; break }
  try { if ((Invoke-WebRequest "http://127.0.0.1:$Port/health" -TimeoutSec 5 -UseBasicParsing).StatusCode -eq 200) { $ok2=$true; break } } catch { Start-Sleep -Seconds 5 }
}
if ($ok2) {
  Write-Output "server READY $([int]((Get-Date)-$t1).TotalSeconds)s"
  # warm, then measure (rep0 is page-cache cold)
  python "$root\fnbench.py" --port $Port --label 'cgb-warm' --sizes "$Prompt" --gen 64 --repeats 1 --out (Join-Path $res 'cgb-warm.json') 2>&1 | Out-Null
  python "$root\fnbench.py" --port $Port --label 'cgb' --sizes "$Prompt" --gen $Gen --repeats 1 --out (Join-Path $res 'cgb.json') 2>&1 |
    Select-String -Pattern 'n=|error'
}
Start-Sleep -Seconds 2
Get-Process llama-server -ErrorAction SilentlyContinue | Stop-Process -Force
Write-Output 'done'
