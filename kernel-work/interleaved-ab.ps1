#requires -Version 5.1
# interleaved-ab.ps1 — high-confidence A/B of two ggml-hip.dll builds by alternating arms.
#
# A single 5-rep measurement has ~±1% spread, which is the same size as the effect we are chasing
# (~2%). Interleaving the arms (base, patch, base, patch) and comparing the aggregate is what makes a
# 2% delta trustworthy: any slow drift (thermal, page cache) hits both arms equally.
#
# The two DLLs are provided as paths; each round we swap the live ggml-hip.dll, launch the server,
# measure SERIAL decode (no drafter), stop, and move on. Requires WSL down (caller's job).
param(
  [string]$BaseDll,
  [string]$PatchDll,
  [int]$Ctx = 32768,
  [int]$Port = 8350,
  [int]$Gen = 256,
  [int]$Repeats = 5,
  [int]$Rounds = 2,
  [string]$Size = "8192"
)
$ErrorActionPreference = 'Continue'
$bin   = 'C:\AI\build\strix-llama-win\build-therock\bin'
$live  = Join-Path $bin 'ggml-hip.dll'
$sdk   = 'C:\AI\sdk\therock1151'
$root  = 'C:\Projects\REV-N-ornith-eval-20260911\kernel-work'
$res   = Join-Path $root 'results'
$model = 'C:\AI\models\qwen38-flash\projfix\Qwen3.8-Flash-Next-IQ4_NL-PROJFIX-00001-of-00009.gguf'

$env:PATH = "$sdk\bin;$sdk\lib\llvm\bin;$env:PATH"
$env:ROCM_PATH = $sdk; $env:HIP_PATH = $sdk
$env:HIP_DEVICE_LIB_PATH = "$sdk\lib\llvm\amdgcn\bitcode"
$env:HSA_OVERRIDE_GFX_VERSION = '11.5.1'

$all = @()

function Run-Arm([string]$which, [string]$dll, [int]$round) {
  Get-Process llama-server -ErrorAction SilentlyContinue | Stop-Process -Force
  Start-Sleep -Seconds 5
  Copy-Item $dll $live -Force
  $a = @('-m',$model,'-dev','ROCm0','-ngl','999','-fa','on','-fit','off','--load-mode','none',
    '-ctk','f16','-ctv','f16','-c',"$Ctx",'-b','2048','-ub','2048','--parallel','1',
    '--host','127.0.0.1','--port',"$Port",'--no-webui','--seed','1234')
  $serr = Join-Path $res "iab-$which-r$round.err"
  $p = Start-Process -FilePath (Join-Path $bin 'llama-server.exe') -ArgumentList $a -PassThru `
        -RedirectStandardOutput (Join-Path $res "iab-$which-r$round.out") -RedirectStandardError $serr -NoNewWindow
  $ok=$false; $t0=Get-Date
  while (((Get-Date)-$t0).TotalSeconds -lt 420) {
    if ($p.HasExited) { Write-Output "[$which r$round] EXITED $($p.ExitCode)"; return $null }
    try { if ((Invoke-WebRequest "http://127.0.0.1:$Port/health" -TimeoutSec 5 -UseBasicParsing).StatusCode -eq 200) { $ok=$true; break } } catch { Start-Sleep -Seconds 4 }
  }
  if (-not $ok) { Write-Output "[$which r$round] NOT READY"; return $null }
  $out = Join-Path $res "iab-$which-r$round.json"
  python "$root\fnbench.py" --port $Port --label "iab-$which-r$round" --sizes $Size --gen $Gen --repeats $Repeats --out $out 2>&1 | Out-Null
  Get-Process llama-server -ErrorAction SilentlyContinue | Stop-Process -Force
  Start-Sleep -Seconds 3
  if (-not (Test-Path $out)) { Write-Output "[$which r$round] no json"; return $null }
  $j = Get-Content $out -Raw | ConvertFrom-Json
  $vals = ($j.rows | Where-Object { $_.rep -gt 0 -and -not $_.error } | ForEach-Object { $_.decode_tps }) | Sort-Object
  if ($vals.Count -eq 0) { return $null }
  $med = $vals[[int]($vals.Count/2)]
  Write-Output ("[$which r$round] decode median={0:N3} t/s  (n={1}, range {2:N2}..{3:N2})" -f $med,$vals.Count,$vals[0],$vals[-1])
  return $med
}

for ($r = 1; $r -le $Rounds; $r++) {
  $b = Run-Arm 'base' $BaseDll $r
  $q = Run-Arm 'patch' $PatchDll $r
  if ($b) { $all += [pscustomobject]@{ arm='base'; round=$r; tps=$b } }
  if ($q) { $all += [pscustomobject]@{ arm='patch'; round=$r; tps=$q } }
}

Write-Output ''
Write-Output '=== aggregate ==='
foreach ($arm in 'base','patch') {
  $v = ($all | Where-Object { $_.arm -eq $arm } | ForEach-Object { $_.tps }) | Sort-Object
  if ($v.Count -gt 0) {
    $med = $v[[int]($v.Count/2)]
    Write-Output ("  {0,-6} median={1:N3} t/s  (rounds: {2})" -f $arm, $med, (($all | Where-Object { $_.arm -eq $arm } | ForEach-Object { '{0:N2}' -f $_.tps }) -join ', '))
  }
}
$bm = (($all | Where-Object { $_.arm -eq 'base' } | ForEach-Object { $_.tps }) | Sort-Object)
$pm = (($all | Where-Object { $_.arm -eq 'patch' } | ForEach-Object { $_.tps }) | Sort-Object)
if ($bm.Count -gt 0 -and $pm.Count -gt 0) {
  $b = $bm[[int]($bm.Count/2)]; $pp = $pm[[int]($pm.Count/2)]
  Write-Output ("  delta = {0:+0.00;-0.00} t/s ({1:+0.0;-0.0}%)" -f ($pp-$b), (100*($pp-$b)/$b))
}
$all | ConvertTo-Json -Depth 4 | Set-Content (Join-Path $res 'interleaved-ab.json')
Write-Output 'done'
