#requires -Version 5.1
# compare-olliehm-mtp.ps1 — test olliehm's MTP operating point (n-max 4, p-min 0.75) on OUR engine.
#
# Why: our n-max 3-8 sweep used the default --spec-draft-p-min (0.0). His published config is
# n-max 4 WITH p-min 0.75, which only proposes high-confidence drafts (hence his 85-100% acceptance).
# That is a different regime and we never tested it. Same model/quant/ub, vary only the MTP flags.
param(
  [int]$Ctx = 262144,
  [int]$Port = 8450,
  [int]$Gen = 256,
  [int]$Repeats = 3,
  [string]$Sizes = "65536"
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
$env:HSA_OVERRIDE_GFX_VERSION = '11.5.1'

$configs = @(
  @{ tag='ours-n2-p000'; nmax='2'; pmin='0.0'  },   # our production config, as baseline
  @{ tag='olliehm-n4-p075'; nmax='4'; pmin='0.75' }, # his published config
  @{ tag='n4-p000'; nmax='4'; pmin='0.0' }           # n-max 4 without the p-min gate (isolates p-min)
)

$out = @()
foreach ($c in $configs) {
  Get-Process llama-server -ErrorAction SilentlyContinue | Stop-Process -Force
  Start-Sleep -Seconds 5
  $a = @('-m',$model,'-md',$head,'-dev','ROCm0','-ngl','999','--n-gpu-layers-draft','999',
    '--spec-type','draft-mtp','--spec-draft-n-max',$c.nmax,'--spec-draft-p-min',$c.pmin,
    '-fa','on','-fit','off','--load-mode','none','-ctk','f16','-ctv','f16',
    '-c',"$Ctx",'-b','8192','-ub','8192','--parallel','1',
    '--host','127.0.0.1','--port',"$Port",'--no-webui','--seed','1234')
  $serr = Join-Path $res "omp-$($c.tag).err"
  Remove-Item $serr -ErrorAction SilentlyContinue
  $p = Start-Process -FilePath $bin -ArgumentList $a -PassThru -RedirectStandardOutput (Join-Path $res "omp-$($c.tag).out") -RedirectStandardError $serr -NoNewWindow
  $ok=$false; $t0=Get-Date
  while (((Get-Date)-$t0).TotalSeconds -lt 600) {
    if ($p.HasExited) { Write-Output "[$($c.tag)] EXITED $($p.ExitCode)"; Get-Content $serr -Tail 6; break }
    try { if ((Invoke-WebRequest "http://127.0.0.1:$Port/health" -TimeoutSec 5 -UseBasicParsing).StatusCode -eq 200) { $ok=$true; break } } catch { Start-Sleep -Seconds 5 }
  }
  if (-not $ok) { Write-Output "[$($c.tag)] NOT READY"; continue }
  Write-Output "[$($c.tag)] ready (n-max=$($c.nmax) p-min=$($c.pmin))"
  python "$root\fnbench.py" --port $Port --label "omp-$($c.tag)" --sizes $Sizes --gen $Gen --repeats $Repeats --out (Join-Path $res "omp-$($c.tag).json") 2>&1 | Select-String 'n=' | ForEach-Object { '  ' + $_.Line.Trim() }
  Get-Process llama-server -ErrorAction SilentlyContinue | Stop-Process -Force
  Start-Sleep -Seconds 3

  $j = Get-Content (Join-Path $res "omp-$($c.tag).json") -Raw | ConvertFrom-Json
  $w = $j.rows | Where-Object { $_.rep -gt 0 -and -not $_.error -and $_.decode_tps }
  if ($w) {
    $d = ($w | ForEach-Object { $_.decode_tps }) | Sort-Object
    $da = ($w | ForEach-Object { $_.draft_n_accepted }) | Measure-Object -Sum
    $dn = ($w | ForEach-Object { $_.draft_n }) | Measure-Object -Sum
    $out += [pscustomobject]@{ tag=$c.tag; nmax=$c.nmax; pmin=$c.pmin
      decode_tps=[math]::Round($d[[int]($d.Count/2)],2)
      acceptance=[math]::Round($da.Sum/$dn.Sum,3) }
  }
}
Write-Output ''
Write-Output '=== MTP operating point comparison (our engine, PROJFIX, -c 262144 -ub 8192) ==='
$out | ForEach-Object { Write-Output ('  {0,-18} n-max={1} p-min={2,-5} decode={3,6:N2} t/s  acceptance={4:P0}' -f $_.tag,$_.nmax,$_.pmin,$_.decode_tps,$_.acceptance) }
$out | ConvertTo-Json -Depth 4 | Set-Content (Join-Path $res 'omp-compare.json')
Write-Output 'done'
