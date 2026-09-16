#requires -Version 5.1
# mtp-rows2-ab.ps1 — the CORRECT rpb test: MTP decode (n-max 2), which runs width-3 verify.
#
# Codex's point: the earlier rpb negative used SERIAL decode = ncols_dst 1, which the patch does not
# touch. The coverage log confirms ncols_dst = 2,3,4,8 execute under MTP n-max 2, so this is the test
# that exercises the change. Same binary, env gate toggled, interleaved arms.
param(
  [int]$Ctx = 32768,
  [int]$Port = 8432,
  [int]$Gen = 256,
  [int]$Repeats = 4,
  [int]$Rounds = 2,
  [string]$Size = "8192"
)
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
$env:HSA_OVERRIDE_GFX_VERSION = '11.5.1'

$all = @()
function Run-Arm([string]$which, [int]$round) {
  Get-Process llama-server -ErrorAction SilentlyContinue | Stop-Process -Force
  Start-Sleep -Seconds 5
  if ($which -eq 'rows2') { $env:GGML_MMVQ_RD2_ROWS2 = '1' } else { Remove-Item Env:GGML_MMVQ_RD2_ROWS2 -ErrorAction SilentlyContinue }
  $a = @('-m',$model,'-md',$head,'-dev','ROCm0','-ngl','999','--n-gpu-layers-draft','999',
    '--spec-type','draft-mtp','--spec-draft-n-max','2','--spec-draft-p-min','0.0',
    '-fa','on','-fit','off','--load-mode','none','-ctk','f16','-ctv','f16',
    '-c',"$Ctx",'-b','2048','-ub','2048','--parallel','1',
    '--host','127.0.0.1','--port',"$Port",'--no-webui','--seed','1234')
  $serr = Join-Path $res "mab-$which-r$round.err"
  Remove-Item $serr -ErrorAction SilentlyContinue
  $p = Start-Process -FilePath $bin -ArgumentList $a -PassThru -RedirectStandardOutput (Join-Path $res "mab-$which-r$round.out") -RedirectStandardError $serr -NoNewWindow
  $ok=$false; $t0=Get-Date
  while (((Get-Date)-$t0).TotalSeconds -lt 420) {
    if ($p.HasExited) { Write-Output "[$which r$round] EXITED $($p.ExitCode)"; return $null }
    try { if ((Invoke-WebRequest "http://127.0.0.1:$Port/health" -TimeoutSec 5 -UseBasicParsing).StatusCode -eq 200) { $ok=$true; break } } catch { Start-Sleep -Seconds 5 }
  }
  if (-not $ok) { Write-Output "[$which r$round] NOT READY"; return $null }
  $out = Join-Path $res "mab-$which-r$round.json"
  python "$root\fnbench.py" --port $Port --label "mab-$which-r$round" --sizes $Size --gen $Gen --repeats $Repeats --out $out 2>&1 | Out-Null
  Get-Process llama-server -ErrorAction SilentlyContinue | Stop-Process -Force
  Start-Sleep -Seconds 3
  if (-not (Test-Path $out)) { return $null }
  $j = Get-Content $out -Raw | ConvertFrom-Json
  $warm = $j.rows | Where-Object { $_.rep -gt 0 -and -not $_.error -and $_.decode_tps }
  if (-not $warm) { return $null }
  $d = ($warm | ForEach-Object { $_.decode_tps }) | Sort-Object
  $med = $d[[int]($d.Count/2)]
  $da = ($warm | ForEach-Object { $_.draft_n_accepted }) | Measure-Object -Sum | Select-Object -ExpandProperty Sum
  $dn = ($warm | ForEach-Object { $_.draft_n }) | Measure-Object -Sum | Select-Object -ExpandProperty Sum
  $acc = if ($dn) { $da / $dn } else { 0 }
  Write-Output ("[$which r$round] MTP decode median={0:N3} t/s  acceptance={1:P1} ({2}/{3})" -f $med, $acc, $da, $dn)
  return [pscustomobject]@{ which=$which; round=$round; tps=$med; acc=$acc }
}

for ($r = 1; $r -le $Rounds; $r++) {
  $b = Run-Arm 'base' $r;   if ($b) { $all += $b }
  $q = Run-Arm 'rows2' $r;  if ($q) { $all += $q }
}
Write-Output ''
Write-Output '=== aggregate (MTP decode, the width-3 verify test) ==='
foreach ($w in 'base','rows2') {
  $v = ($all | Where-Object { $_.which -eq $w } | ForEach-Object { $_.tps }) | Sort-Object
  $av = ($all | Where-Object { $_.which -eq $w } | ForEach-Object { $_.acc }) | Sort-Object
  if ($v.Count -gt 0) { Write-Output ("  {0,-6} median={1:N3} t/s  acc={2:P1}  rounds: {3}" -f $w, $v[[int]($v.Count/2)], $av[[int]($av.Count/2)], (($all | Where-Object { $_.which -eq $w } | ForEach-Object { '{0:N2}' -f $_.tps }) -join ', ')) }
}
$bm = ($all | Where-Object { $_.which -eq 'base' } | ForEach-Object { $_.tps }) | Sort-Object
$rm = ($all | Where-Object { $_.which -eq 'rows2' } | ForEach-Object { $_.tps }) | Sort-Object
if ($bm.Count -gt 0 -and $rm.Count -gt 0) {
  $b = $bm[[int]($bm.Count/2)]; $rr = $rm[[int]($rm.Count/2)]
  Write-Output ("  delta = {0:+0.00;-0.00} t/s ({1:+0.0;-0.0}%)" -f ($rr-$b), (100*($rr-$b)/$b))
}
$all | ConvertTo-Json -Depth 4 | Set-Content (Join-Path $res 'mtp-rows2-ab.json')
Write-Output 'done'
