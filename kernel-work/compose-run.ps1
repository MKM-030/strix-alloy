#requires -Version 5.1
# compose-run.ps1 — per-op composition, with env passed through cmd 'set' so it CANNOT be lost,
# and with a hard gate: no rows = no numbers.
param([int]$Prompt = 512, [int]$Gen = 512, [int]$Ctx = 4096, [int]$Port = 8295)
$ErrorActionPreference = 'Continue'
$bin  = 'C:\AI\build\strix-llama-win\build-therock\bin\llama-server.exe'
$sdk  = 'C:\AI\sdk\therock1151'
$root = 'C:\Projects\REV-N-ornith-eval-20260911\kernel-work'
$res  = Join-Path $root 'results'
$model = 'C:\AI\models\qwen38-flash\projfix\Qwen3.8-Flash-Next-IQ4_NL-PROJFIX-00001-of-00009.gguf'
$head  = 'C:\AI\models\qwen38-flash\projfix\mtp-Qwen3.8-Flash-Next-shared-Q8_0.gguf'

Get-Process llama-server -ErrorAction SilentlyContinue | Stop-Process -Force
Start-Sleep -Seconds 4

$serr = Join-Path $res 'cr.err'; $sout = Join-Path $res 'cr.out'
Remove-Item $serr,$sout -ErrorAction SilentlyContinue

$args = @('-m',$model,'-dev','ROCm0','-ngl','999','-fa','on','-fit','off','--load-mode','none',
  '-ctk','f16','-ctv','f16','-c',"$Ctx",'-b','2048','-ub','2048','--parallel','1',
  '--host','127.0.0.1','--port',"$Port",'--no-webui') -join ' '

# env INSIDE the child via cmd set: opaque to the parent shell
$line = 'set "PATH=' + $sdk + '\bin;' + $sdk + '\lib\llvm\bin;%PATH%"' +
        ' && set "ROCM_PATH=' + $sdk + '"' +
        ' && set "HIP_PATH=' + $sdk + '"' +
        ' && set "HIP_DEVICE_LIB_PATH=' + $sdk + '\lib\llvm\amdgcn\bitcode"' +
        ' && set "GGML_HIP_ENABLE_UNIFIED_MEMORY=1"' +
        ' && set "HSA_OVERRIDE_GFX_VERSION=11.5.1"' +
        ' && set "LLAMA_OP_TIMING=1"' +
        ' && set "GGML_CUDA_DISABLE_GRAPHS=1"' +
        ' && set "LLAMA_OP_TIMING_EVERY=1"' +
        ' && "' + $bin + '" ' + $args

Write-Output "launching via: cmd /c (set ... && llama-server)"
$p = Start-Process -FilePath 'cmd.exe' -ArgumentList @('/c', $line) -PassThru `
     -RedirectStandardOutput $sout -RedirectStandardError $serr -NoNewWindow
$ok=$false; $t0=Get-Date
while (((Get-Date)-$t0).TotalSeconds -lt 900) {
  if ($p.HasExited) { Write-Output "EXITED $($p.ExitCode)"; break }
  try { if ((Invoke-WebRequest "http://127.0.0.1:$Port/health" -TimeoutSec 5 -UseBasicParsing).StatusCode -eq 200) { $ok=$true; break } } catch { Start-Sleep -Seconds 5 }
}
if ($ok) {
  Write-Output "READY $([int]((Get-Date)-$t0).TotalSeconds)s"
  python "$root\fnbench.py" --port $Port --label 'cr' --sizes "$Prompt" --gen $Gen --repeats 1 `
    --out (Join-Path $res 'cr.json') 2>&1 | Select-String -Pattern 'n=|error'
}
Start-Sleep -Seconds 2
Get-Process llama-server -ErrorAction SilentlyContinue | Stop-Process -Force
Get-Process cmd -ErrorAction SilentlyContinue | Where-Object { $_.Id -eq $p.Id } | Stop-Process -Force
Start-Sleep -Seconds 3

# ---- parse + gate -----------------------------------------------------------------------------
function ReadShared([string]$f) {
  if (-not (Test-Path $f)) { return '' }
  try { $fs=[IO.File]::Open($f,'Open','Read','ReadWrite'); $sr=New-Object IO.StreamReader($fs); $t=$sr.ReadToEnd(); $sr.Close(); $fs.Close(); $t } catch { '' }
}
$t = ReadShared $serr
$lines = ($t -replace "`r", '') -split "`n"
$hdrs = ($lines | Where-Object { $_ -match 'OP_TIMING aggregate' }).Count
$errs = ($lines | Where-Object { $_ -match 'ROCm error|GET_ROWS failed|abort|assert' }).Count
$graphline = ($lines | Where-Object { $_ -match 'graphs reused' } | Select-Object -Last 1)

Write-Output ''
Write-Output '=== GATE ==='
Write-Output ("  op summaries={0}  errors={1}" -f $hdrs, $errs)
if ($graphline) { Write-Output ("  {0}" -f $graphline.Trim()) }

$blocks = @(); $cur = @()
foreach ($l in $lines) {
  if ($l -match '^\s*\S+\|\S*\s+n=\d+\s+total=') { $cur += $l }
  elseif ($cur.Count -gt 0) { $blocks += ,$cur; $cur = @() }
}
if ($cur.Count -gt 0) { $blocks += ,$cur }
$rows = @()
if ($blocks.Count -gt 0) {
  foreach ($l in $blocks[-1]) {
    if ($l -match '^\s*(\S+)\|(\S*)\s+n=(\d+)\s+total=\s*([\d.]+)ms\s+avg=\s*([\d.]+)us') {
      $rows += [pscustomobject]@{ op="$($Matches[1])|$($Matches[2])"; n=[int]$Matches[3]; ms=[double]$Matches[4] }
    }
  }
}
$tot = ($rows | Measure-Object ms -Sum).Sum
$dec_ms = $null
if (Test-Path (Join-Path $res 'cr.json')) {
  try { $j = Get-Content (Join-Path $res 'cr.json') -Raw | ConvertFrom-Json; $dec_ms = [double]$j.rows[0].predicted_ms } catch {}
}

if ($rows.Count -eq 0) {
  Write-Output ''
  Write-Output 'RESULT: NO DATA. Zero op rows -> nothing to report, and this is NOT a pass.'
} else {
  Write-Output ''
  Write-Output ("=== composition, graphs OFF ({0} rows, {1:N1} ms tracked) ===" -f $rows.Count, $tot)
  if ($dec_ms) { Write-Output ("  measured decode wall {0:N1} ms  -> tracked/wall {1:N2}x" -f $dec_ms, ($tot/$dec_ms)) }
  Write-Output ''
  $rows | Group-Object { ($_.op -split '\|')[0] } | ForEach-Object {
      [pscustomobject]@{ op=$_.Name; ms=($_.Group|Measure-Object ms -Sum).Sum; n=($_.Group|Measure-Object n -Sum).Sum }
  } | Sort-Object ms -Descending | Select-Object -First 20 | ForEach-Object {
      Write-Output ("  {0,-24} n={1,-9} {2,9:N2} ms  {3,5:N1}%" -f $_.op, $_.n, $_.ms, (100.0*$_.ms/$tot))
  }
}
