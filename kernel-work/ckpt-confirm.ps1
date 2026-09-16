#requires -Version 5.1
# ckpt-confirm.ps1 — paired, INTERLEAVED A/B: does --ctx-checkpoints change our MTP decode?
#
# Why this exists: the first his-config-bench run showed arm A (no checkpoints) at 47% acceptance /
# 29.25 t/s and arm D (with checkpoints) at 65% / 33.01 t/s. But an EARLIER run (omp) measured the same
# arm-A config at 65% / 33.46. So either checkpointing helps, or our MTP acceptance is unstable between
# runs. Only an interleaved A/B (A,D,A,D) can separate those, because drift then hits both arms.
param(
  [int]$Ctx = 262144,
  [int]$Port = 8462,
  [int]$Gen = 256,
  [int]$Repeats = 2,
  [int]$Rounds = 2,
  [string]$Size = "65536",
  [int]$Checkpoints = 8
)
$ErrorActionPreference = 'Continue'
$bin  = 'C:\AI\build\strix-llama-win\build-therock\bin\llama-server.exe'
$sdk  = 'C:\AI\sdk\therock1151'
$root = 'C:\Projects\strix-alloy\kernel-work'
$res  = Join-Path $root 'results'
$model = 'C:\AI\models\qwen38-flash\projfix\Qwen3.8-Flash-Next-IQ4_NL-PROJFIX-00001-of-00009.gguf'
$head  = 'C:\AI\models\qwen38-flash\projfix\mtp-Qwen3.8-Flash-Next-shared-Q8_0.gguf'

$env:PATH = "$sdk\bin;$sdk\lib\llvm\bin;$env:PATH"
$env:ROCM_PATH = $sdk; $env:HIP_PATH = $sdk
$env:HIP_DEVICE_LIB_PATH = "$sdk\lib\llvm\amdgcn\bitcode"
$env:GGML_HIP_ENABLE_UNIFIED_MEMORY = '1'
$env:HSA_OVERRIDE_GFX_VERSION = '11.5.1'

$all = @()
function Run-Arm([string]$which, [int]$round) {
  Get-Process llama-server -ErrorAction SilentlyContinue | Stop-Process -Force
  Start-Sleep -Seconds 5
  $extra = if ($which -eq 'ckpt') { @('--ctx-checkpoints',"$Checkpoints") } else { @() }
  $a = @('-m',$model,'-md',$head,'-dev','ROCm0','-ngl','999','--n-gpu-layers-draft','999',
    '--spec-type','draft-mtp','--spec-draft-n-max','2','--spec-draft-p-min','0.0',
    '-fa','on','-fit','off','--load-mode','none','-ctk','f16','-ctv','f16',
    '-c',"$Ctx",'-b','8192','-ub','8192','--parallel','1',
    '--host','127.0.0.1','--port',"$Port",'--no-webui','--seed','1234') + $extra
  $serr = Join-Path $res "ckc-$which-r$round.err"
  Remove-Item $serr -ErrorAction SilentlyContinue
  $p = Start-Process -FilePath $bin -ArgumentList $a -PassThru -RedirectStandardOutput (Join-Path $res "ckc-$which-r$round.out") -RedirectStandardError $serr -NoNewWindow
  $ok=$false; $t0=Get-Date
  while (((Get-Date)-$t0).TotalSeconds -lt 600) {
    if ($p.HasExited) { Write-Output "[$which r$round] EXITED $($p.ExitCode)"; return $null }
    try { if ((Invoke-WebRequest "http://127.0.0.1:$Port/health" -TimeoutSec 5 -UseBasicParsing).StatusCode -eq 200) { $ok=$true; break } } catch { Start-Sleep -Seconds 5 }
  }
  if (-not $ok) { Write-Output "[$which r$round] NOT READY"; return $null }
  $out = Join-Path $res "ckc-$which-r$round.json"
  python "$root\fnbench.py" --port $Port --label "ckc-$which-r$round" --sizes $Size --gen $Gen --repeats $Repeats --out $out 2>&1 | Out-Null
  Get-Process llama-server -ErrorAction SilentlyContinue | Stop-Process -Force
  Start-Sleep -Seconds 3
  if (-not (Test-Path $out)) { return $null }
  $j = Get-Content $out -Raw | ConvertFrom-Json
  $w = $j.rows | Where-Object { $_.rep -gt 0 -and -not $_.error -and $_.decode_tps }
  if (-not $w) { return $null }
  $d = ($w | ForEach-Object { $_.decode_tps }) | Sort-Object
  $da = ($w | ForEach-Object { $_.draft_n_accepted }) | Measure-Object -Sum
  $dn = ($w | ForEach-Object { $_.draft_n }) | Measure-Object -Sum
  $med = $d[[int]($d.Count/2)]; $acc = $da.Sum/$dn.Sum
  Write-Output ("[$which r$round] decode={0,6:N2} t/s  acceptance={1,4:P0}  ({2}/{3} drafts)" -f $med,$acc,$da.Sum,$dn.Sum)
  return [pscustomobject]@{ which=$which; round=$round; tps=$med; acc=$acc; drafts=$dn.Sum; accepted=$da.Sum }
}

for ($r = 1; $r -le $Rounds; $r++) {
  Write-Output "===== round $r ====="
  $a1 = Run-Arm 'plain' $r; if ($a1) { $all += $a1 }
  $a2 = Run-Arm 'ckpt'  $r; if ($a2) { $all += $a2 }
}
Write-Output ''
Write-Output '=== interleaved A/B: --ctx-checkpoints effect on our MTP decode ==='
foreach ($w in 'plain','ckpt') {
  $v = ($all | Where-Object { $_.which -eq $w } | ForEach-Object { $_.tps }) | Sort-Object
  $ac = ($all | Where-Object { $_.which -eq $w } | ForEach-Object { $_.acc }) | Sort-Object
  if ($v.Count) { Write-Output ('  {0,-6} median={1,6:N2} t/s  acc(median)={2,4:P0}  runs: {3}' -f $w, $v[[int]($v.Count/2)], $ac[[int]($ac.Count/2)], (($all | Where-Object { $_.which -eq $w } | ForEach-Object { '{0:N2}/{1:P0}' -f $_.tps,$_.acc }) -join ', ')) }
}
$pv = ($all | Where-Object { $_.which -eq 'plain' } | ForEach-Object { $_.tps }) | Sort-Object
$cv = ($all | Where-Object { $_.which -eq 'ckpt' }  | ForEach-Object { $_.tps }) | Sort-Object
if ($pv.Count -and $cv.Count) {
  $p = $pv[[int]($pv.Count/2)]; $c = $cv[[int]($cv.Count/2)]
  Write-Output ('  delta = {0:+0.00;-0.00} t/s ({1:+0.0;-0.0}%)' -f ($c-$p), (100*($c-$p)/$p))
}
$all | ConvertTo-Json -Depth 4 | Set-Content (Join-Path $res 'ckpt-confirm.json')
Write-Output 'done'
