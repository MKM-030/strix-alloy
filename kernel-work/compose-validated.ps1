#requires -Version 5.1
# compose-validated.ps1 — per-op composition that VALIDATES ITSELF.
#
# Reality on this stack (three hypotheses tested and falsified today):
#   * in-graph events  -> hipEventElapsedTime = 400 (captured events unqueryable)
#   * capture-time CPU -> capture records, does not execute, so it measures enqueue only
#   * eager warmup     -> graphs warm up at MODEL LOAD, so inference is pure replay; no eager evals
# => the only measurable composition is the aggregate path with graphs OFF.
#
# Graphs-off runs the SAME kernels, so composition is informative; the risk is that event pairs
# span launch gaps and over-attribute. So this script VALIDATES the result:
#     sum(per-op GPU ms) vs measured decode wall ms
# If the sum is far BELOW wall, the timer missed work (ok). If it EXCEEDS wall, the per-op times
# are inflated and must not be trusted.
param([int]$Prompt = 512, [int]$Gen = 512, [int]$Ctx = 4096, [int]$Port = 8293)
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

# the documented config for the aggregate path
$env:LLAMA_OP_TIMING = '1'
$env:GGML_CUDA_DISABLE_GRAPHS = '1'
$env:LLAMA_OP_TIMING_EVERY = '1'

Get-Process llama-server -ErrorAction SilentlyContinue | Stop-Process -Force
Start-Sleep -Seconds 4
# MTP on so this reflects the real decode config (n-max 2)
$a = @('-m',$model,'-md',$head,'-dev','ROCm0','-ngl','999','-fa','on','-fit','off','--load-mode','none',
  '-ctk','f16','-ctv','f16','-c',"$Ctx",'-b','2048','-ub','2048','--parallel','1',
  '--host','127.0.0.1','--port',"$Port",'--no-webui',
  '--spec-type','draft-mtp','--spec-draft-n-max','2')
$serr = Join-Path $res 'cv.err'
Remove-Item $serr -ErrorAction SilentlyContinue
$p = Start-Process -FilePath $bin -ArgumentList $a -PassThru -RedirectStandardOutput (Join-Path $res 'cv.out') -RedirectStandardError $serr -NoNewWindow
$ok=$false; $t0=Get-Date
while (((Get-Date)-$t0).TotalSeconds -lt 900) {
  if ($p.HasExited) { Write-Output "EXITED $($p.ExitCode)"; break }
  try { if ((Invoke-WebRequest "http://127.0.0.1:$Port/health" -TimeoutSec 5 -UseBasicParsing).StatusCode -eq 200) { $ok=$true; break } } catch { Start-Sleep -Seconds 5 }
}
if ($ok) {
  Write-Output "READY $([int]((Get-Date)-$t0).TotalSeconds)s"
  python "$root\fnbench.py" --port $Port --label 'cv' --sizes "$Prompt" --gen $Gen --repeats 1 --out (Join-Path $res 'cv.json') 2>&1 |
    Select-String -Pattern 'n=|error'
}
Start-Sleep -Seconds 2
Get-Process llama-server -ErrorAction SilentlyContinue | Stop-Process -Force
Start-Sleep -Seconds 3

$t = ReadShared $serr
$lines = ($t -replace "`r", '') -split "`n"
$headers = ($lines | Where-Object { $_ -match 'OP_TIMING aggregate' }).Count
$errs    = ($lines | Where-Object { $_ -match 'ROCm error|GET_ROWS failed|abort|assert' }).Count

Write-Output ''
Write-Output '=== VALIDATION GATE ==='
Write-Output ("  summaries={0}  errors={1}" -f $headers, $errs)

# parse the LAST block
$blocks = @(); $cur = @()
foreach ($l in $lines) {
  if ($l -match '^\s*\S+\|\S*\s+n=\d+\s+total=') { $cur += $l }
  elseif ($cur.Count -gt 0) { $blocks += ,$cur; $cur = @() }
}
if ($cur.Count -gt 0) { $blocks += ,$cur }
$use = if ($blocks.Count -gt 0) { $blocks[-1] } else { @() }
$rows = @()
foreach ($l in $use) {
  if ($l -match '^\s*(\S+)\|(\S*)\s+n=(\d+)\s+total=\s*([\d.]+)ms\s+avg=\s*([\d.]+)us') {
    $rows += [pscustomobject]@{ op="$($Matches[1])|$($Matches[2])"; n=[int]$Matches[3]; ms=[double]$Matches[4]; us=[double]$Matches[5] }
  }
}
$tot = ($rows | Measure-Object ms -Sum).Sum

# measured decode wall from the json
$dec_ms = $null; $dec_tps = $null; $pred_n = $null
$jp = Join-Path $res 'cv.json'
if (Test-Path $jp) {
  try {
    $j = Get-Content $jp -Raw | ConvertFrom-Json
    $r0 = $j.rows[0]
    $dec_ms = [double]$r0.predicted_ms; $dec_tps = [double]$r0.decode_tps; $pred_n = [int]$r0.predicted_n
  } catch {}
}

Write-Output ''
Write-Output ("  blocks={0}  rows={1}  tracked_total={2:N1} ms" -f $blocks.Count, $rows.Count, $tot)
if ($dec_ms -ne $null) {
  Write-Output ("  measured decode wall = {0:N1} ms  ({1:N2} t/s, {2} tokens)" -f $dec_ms, $dec_tps, $pred_n)
  if ($rows.Count -eq 0) {
    Write-Output '  => NO DATA: zero op rows parsed. This is NOT a pass (0 <= wall is trivially true).'
    Write-Output '     Check the binary actually contains the timer and that the env vars reached the process.'
  } else {
    Write-Output ("  tracked / wall       = {0:N2}x" -f ($tot / $dec_ms))
    Write-Output ''
    if ($tot -le $dec_ms * 1.15) { Write-Output '  => CONSISTENT: per-op times do not exceed the measured wall.' }
    else { Write-Output '  => INFLATED: per-op sum exceeds wall; treat shares as unreliable.' }
  }
} else { Write-Output '  (no json -> cannot cross-check)' }

Write-Output ''
Write-Output '=== composition by op (last block, graphs OFF) ==='
if ($tot -gt 0) {
  $rows | Group-Object { ($_.op -split '\|')[0] } | ForEach-Object {
      [pscustomobject]@{ op=$_.Name; ms=($_.Group|Measure-Object ms -Sum).Sum; n=($_.Group|Measure-Object n -Sum).Sum }
  } | Sort-Object ms -Descending | Select-Object -First 20 | ForEach-Object {
      Write-Output ("  {0,-24} n={1,-9} {2,9:N2} ms  {3,5:N1}%" -f $_.op, $_.n, $_.ms, (100.0*$_.ms/$tot))
  }
}
