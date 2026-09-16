#requires -Version 5.1
# his-config-bench.ps1 — benchmark with the adjustments learned from olliehm's repo applied.
#
# What we take from his repo and why (see docs/benchmarks/engine-comparison-vs-olliehm-20260916.md):
#   1. --ctx-checkpoints + --checkpoint-min-step : he documents recurrent-state checkpointing as
#      MANDATORY for MTP on gfx1151 (his pre-trial without it: 21.4 -> 5.1 t/s). Our fork carries the
#      mechanism but we never swept the count.
#   2. --spec-draft-n-max 4 --spec-draft-p-min 0.75 : his published acceptance config (85-100%).
#   3. his batch shape -b/-ub 2048 (his current setting; we had been using 8192).
#
# Arms are measured at the SAME depth so they are comparable, and each is a full server restart.
param(
  [int]$Ctx = 262144,
  [int]$Port = 8460,
  [int]$Gen = 256,
  [int]$Repeats = 3,
  [string]$Sizes = "65536",
  [int]$Checkpoints = 8,
  [int]$CacheRam = 3072
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

# arm id -> extra args + a label describing what changed
$arms = @(
  @{ tag='A-ours';        note='baseline: n-max 2, p-min 0.0, ub 8192, ckpt default';
     extra=@(); ub='8192' },
  @{ tag='B-his-mtp';     note='his MTP point: n-max 4, p-min 0.75, ub 2048';
     extra=@('--spec-draft-n-max','4','--spec-draft-p-min','0.75'); ub='2048' },
  @{ tag='C-his-mtp+ckpt'; note='his MTP point + ctx-checkpoints (his documented requirement)';
     extra=@('--spec-draft-n-max','4','--spec-draft-p-min','0.75','--ctx-checkpoints',"$Checkpoints",'--cache-ram',"$CacheRam"); ub='2048' },
  @{ tag='D-ours+ckpt';   note='our MTP point + checkpoints (isolates the checkpoint effect)';
     extra=@('--spec-draft-n-max','2','--spec-draft-p-min','0.0','--ctx-checkpoints',"$Checkpoints",'--cache-ram',"$CacheRam"); ub='8192' }
)

$out = @()
foreach ($a in $arms) {
  Get-Process llama-server -ErrorAction SilentlyContinue | Stop-Process -Force
  Start-Sleep -Seconds 5
  $args_ = @('-m',$model,'-md',$head,'-dev','ROCm0','-ngl','999','--n-gpu-layers-draft','999',
    '--spec-type','draft-mtp','-fa','on','-fit','off','--load-mode','none','-ctk','f16','-ctv','f16',
    '-c',"$Ctx",'-b',$a.ub,'-ub',$a.ub,'--parallel','1',
    '--host','127.0.0.1','--port',"$Port",'--no-webui','--seed','1234') + $a.extra
  $serr = Join-Path $res "hcb-$($a.tag).err"
  Remove-Item $serr -ErrorAction SilentlyContinue
  $p = Start-Process -FilePath $bin -ArgumentList $args_ -PassThru -RedirectStandardOutput (Join-Path $res "hcb-$($a.tag).out") -RedirectStandardError $serr -NoNewWindow
  $ok=$false; $t0=Get-Date
  while (((Get-Date)-$t0).TotalSeconds -lt 600) {
    if ($p.HasExited) { Write-Output "[$($a.tag)] EXITED $($p.ExitCode)"; Get-Content $serr -Tail 6; break }
    try { if ((Invoke-WebRequest "http://127.0.0.1:$Port/health" -TimeoutSec 5 -UseBasicParsing).StatusCode -eq 200) { $ok=$true; break } } catch { Start-Sleep -Seconds 5 }
  }
  if (-not $ok) { Write-Output "[$($a.tag)] NOT READY"; continue }
  Write-Output "[$($a.tag)] ready - $($a.note)"
  python "$root\fnbench.py" --port $Port --label "hcb-$($a.tag)" --sizes $Sizes --gen $Gen --repeats $Repeats --out (Join-Path $res "hcb-$($a.tag).json") 2>&1 | Select-String 'n=' | ForEach-Object { '  ' + $_.Line.Trim() }
  Get-Process llama-server -ErrorAction SilentlyContinue | Stop-Process -Force
  Start-Sleep -Seconds 3

  $jsonPath = Join-Path $res "hcb-$($a.tag).json"
  if (Test-Path $jsonPath) {
    $j = Get-Content $jsonPath -Raw | ConvertFrom-Json
    $w = $j.rows | Where-Object { $_.rep -gt 0 -and -not $_.error -and $_.decode_tps }
    if ($w) {
      $d = ($w | ForEach-Object { $_.decode_tps }) | Sort-Object
      $pf = ($w | ForEach-Object { $_.prefill_tps }) | Sort-Object
      $da = ($w | ForEach-Object { $_.draft_n_accepted }) | Measure-Object -Sum
      $dn = ($w | ForEach-Object { $_.draft_n }) | Measure-Object -Sum
      $out += [pscustomobject]@{ tag=$a.tag; note=$a.note; ub=$a.ub
        prefill_tps=[math]::Round($pf[[int]($pf.Count/2)],1)
        decode_tps=[math]::Round($d[[int]($d.Count/2)],2)
        acceptance=[math]::Round($da.Sum/$dn.Sum,3) }
    }
  }
}
Write-Output ''
Write-Output '=== adjustments from olliehm, measured on our engine (same depth, same prompt) ==='
$out | ForEach-Object { Write-Output ('  {0,-16} ub={1,-5} prefill={2,7:N1} decode={3,6:N2} t/s acc={4,4:P0}  {5}' -f $_.tag,$_.ub,$_.prefill_tps,$_.decode_tps,$_.acceptance,$_.note) }
$out | ConvertTo-Json -Depth 4 | Set-Content (Join-Path $res 'his-config-bench.json')
Write-Output 'done'
