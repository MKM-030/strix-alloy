#requires -Version 5.1
# ub-mtp-sweep.ps1 — can we use a large ubatch WITH the MTP draft head?
#
# Prior work forced `-b/-ub 2048` with a draft attached ("Bug A"). The B1 repro showed ub 8192
# LOADS with a draft on the current binary -- but load alone is not enough: Bug A's error
# ("invalid vector subscript") could fire at first graph build, i.e. the first real generation.
# So this script both loads AND generates for each ubatch. If a large ubatch works with MTP, we get
# the fast prefill shape (ub 16384 ~= 1057 t/s @16k) together with MTP decode, instead of trading
# one for the other.
param(
  [int]$Ctx = 32768,
  [int]$Port = 8310,
  [int]$Gen = 128,
  [int]$Repeats = 3,
  [string]$Ubs = "2048,8192,16384",
  [string]$Sizes = "1024,8192,16384",
  [string]$NMax = "2"
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
$env:GGML_HIP_ENABLE_UNIFIED_MEMORY = '1'
$env:HSA_OVERRIDE_GFX_VERSION = '11.5.1'

function Try-Ub([int]$ub) {
  $tag = "ub$ub"
  Get-Process llama-server -ErrorAction SilentlyContinue | Stop-Process -Force
  Start-Sleep -Seconds 5
  $a = @('-m',$model,'-dev','ROCm0','-ngl','999','-fa','on','-fit','off','--load-mode','none',
    '-ctk','f16','-ctv','f16','-c',"$Ctx",'-b',"$ub",'-ub',"$ub",'--parallel','1',
    '--host','127.0.0.1','--port',"$Port",'--no-webui','--seed','1234',
    '-md',$head,'--spec-type','draft-mtp','--spec-draft-n-max',"$NMax",'--spec-draft-p-min','0.0',
    '--n-gpu-layers-draft','999')
  $serr = Join-Path $res "ubm-$tag.err"; $sout = Join-Path $res "ubm-$tag.out"
  Remove-Item $serr,$sout -ErrorAction SilentlyContinue
  $p = Start-Process -FilePath $bin -ArgumentList $a -PassThru -RedirectStandardOutput $sout -RedirectStandardError $serr -NoNewWindow
  $ok=$false; $t0=Get-Date
  while (((Get-Date)-$t0).TotalSeconds -lt 420) {
    if ($p.HasExited) { break }
    try { if ((Invoke-WebRequest "http://127.0.0.1:$Port/health" -TimeoutSec 5 -UseBasicParsing).StatusCode -eq 200) { $ok=$true; break } } catch { Start-Sleep -Seconds 4 }
  }
  if (-not $ok) {
    $txt = ''
    foreach ($f in @($serr,$sout)) { if (Test-Path $f) { $txt += (Get-Content $f -Raw -ErrorAction SilentlyContinue) } }
    $fatal = (($txt -split "`n") | Where-Object { $_ -match 'invalid vector subscript|error loading model|failed to load|assert|abort|out of memory|failed to alloc' } | Select-Object -First 2)
    Write-Output "[$tag] LOAD FAILED exit=$($p.ExitCode)"
    foreach ($l in $fatal) { Write-Output ("      | " + $l.Trim()) }
    Get-Process llama-server -ErrorAction SilentlyContinue | Stop-Process -Force
    Start-Sleep -Seconds 3
    return [pscustomobject]@{ ub=$ub; loads=$false; gen_ok=$false; note=($fatal -join ' | ') }
  }
  # real generation: this is where Bug A would fire at graph build if it were still live
  $genOk = $true; $err = $null
  try {
    python "$root\fnbench.py" --port $Port --label "ubm-$tag" --sizes $Sizes --gen $Gen --repeats $Repeats `
      --out (Join-Path $res "ubm-$tag.json") 2>&1 | Tee-Object -FilePath (Join-Path $res "ubm-$tag.log") | Out-Null
  } catch { $genOk = $false; $err = "$_" }
  # check the rows actually contain numbers
  $j = $null
  if (Test-Path (Join-Path $res "ubm-$tag.json")) { $j = Get-Content (Join-Path $res "ubm-$tag.json") -Raw | ConvertFrom-Json }
  $rows = if ($j) { $j.rows } else { @() }
  $anyErr = @($rows | Where-Object { $_.error })
  if ($anyErr.Count -gt 0) { $genOk = $false; $err = $anyErr[0].error }
  foreach ($r in $rows) {
    $acc = if ($r.draft_n) { "acc=$($r.draft_n_accepted)/$($r.draft_n)" } else { "acc=n/a" }
    Write-Output ("[$tag] n=$($r.target_n) rep=$($r.rep) prefill={0} t/s decode={1} t/s {2}" -f `
      ($(if($r.prefill_tps){[math]::Round($r.prefill_tps,1)}else{'ERR'})), `
      ($(if($r.decode_tps){[math]::Round($r.decode_tps,2)}else{'ERR'})), $acc)
  }
  Get-Process llama-server -ErrorAction SilentlyContinue | Stop-Process -Force
  Start-Sleep -Seconds 3
  return [pscustomobject]@{ ub=$ub; loads=$true; gen_ok=$genOk; note=$err; rows=$rows }
}

$out = @()
foreach ($u in ($Ubs.Split(',') | ForEach-Object { [int]$_.Trim() })) {
  Write-Output "==== ubatch $u (MTP n-max $NMax) ===="
  $out += Try-Ub $u
  Write-Output ''
}
$out | ConvertTo-Json -Depth 6 | Set-Content (Join-Path $res 'ub-mtp-sweep.json')
Write-Output 'done'
