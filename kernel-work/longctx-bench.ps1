#requires -Version 5.1
# longctx-bench.ps1 — prefill + decode ladder up to a large context (e.g. 251k).
#
# WSL MUST be down before running this: vmmemWSL holds host RAM and has corrupted prefill numbers
# three times (see ilintar-rebase-result-20260915.md). The caller's job.
#
# Two shapes:
#   prefill  (default): -b/-ub <Ub> no drafter      -> max prefill t/s and serial decode t/s
#   -Draft            : adds the shared MTP head    -> MTP decode t/s + acceptance
#
# Sizes ascend so a memory/alloc failure at extreme depth still leaves the shallower data.
param(
  [int]$Ctx = 262144,
  [int]$Port = 8360,
  [int]$Gen = 64,
  [int]$Ub = 16384,
  [int]$Repeats = 2,
  [int]$RepeatsBig = 1,
  [int]$BigThreshold = 131072,
  [string]$Sizes = "16384,65536,131072,196608,251904",
  [string]$Label = "lc-prefill",
  [switch]$Draft,
  [int]$NMax = 2,
  [string]$OutDir = "results"
)
$ErrorActionPreference = 'Continue'
$bin  = 'C:\AI\build\strix-llama-win\build-therock\bin\llama-server.exe'
$sdk  = 'C:\AI\sdk\therock1151'
$root = 'C:\Projects\REV-N-ornith-eval-20260911\kernel-work'
$res  = Join-Path $root $OutDir
$model = 'C:\AI\models\qwen38-flash\projfix\Qwen3.8-Flash-Next-IQ4_NL-PROJFIX-00001-of-00009.gguf'
$head  = 'C:\AI\models\qwen38-flash\projfix\mtp-Qwen3.8-Flash-Next-shared-Q8_0.gguf'

$env:PATH = "$sdk\bin;$sdk\lib\llvm\bin;$env:PATH"
$env:ROCM_PATH = $sdk; $env:HIP_PATH = $sdk
$env:HIP_DEVICE_LIB_PATH = "$sdk\lib\llvm\amdgcn\bitcode"
$env:GGML_HIP_ENABLE_UNIFIED_MEMORY = '1'
$env:HSA_OVERRIDE_GFX_VERSION = '11.5.1'

Get-Process llama-server -ErrorAction SilentlyContinue | Stop-Process -Force
Start-Sleep -Seconds 5

$a = @('-m',$model,'-dev','ROCm0','-ngl','999','-fa','on','-fit','off','--load-mode','none',
  '-ctk','f16','-ctv','f16','-c',"$Ctx",'-b',"$Ub",'-ub',"$Ub",'--parallel','1',
  '--host','127.0.0.1','--port',"$Port",'--no-webui','--seed','1234')
if ($Draft) {
  $a += @('-md',$head,'--spec-type','draft-mtp','--spec-draft-n-max',"$NMax",'--spec-draft-p-min','0.0','--n-gpu-layers-draft','999')
}
$serr = Join-Path $res "lc-$Label.err"; $sout = Join-Path $res "lc-$Label.out"
Remove-Item $serr,$sout -ErrorAction SilentlyContinue
Write-Output "[$Label] launch: -c $Ctx -b/-ub $Ub draft=$Draft nmax=$NMax"
$p = Start-Process -FilePath $bin -ArgumentList $a -PassThru -RedirectStandardOutput $sout -RedirectStandardError $serr -NoNewWindow
$ok=$false; $t0=Get-Date
while (((Get-Date)-$t0).TotalSeconds -lt 900) {
  if ($p.HasExited) {
    Write-Output "[$Label] EXITED $($p.ExitCode) after $([int]((Get-Date)-$t0).TotalSeconds)s"
    Get-Content $serr -Tail 12 -ErrorAction SilentlyContinue
    return
  }
  try { if ((Invoke-WebRequest "http://127.0.0.1:$Port/health" -TimeoutSec 5 -UseBasicParsing).StatusCode -eq 200) { $ok=$true; break } } catch { Start-Sleep -Seconds 5 }
}
if (-not $ok) { Write-Output "[$Label] NOT READY"; Get-Content $serr -Tail 12; return }
Write-Output "[$Label] ready $([int]((Get-Date)-$t0).TotalSeconds)s"
# warm the page cache / mmap
python "$root\fnbench.py" --port $Port --label "lcwarm-$Label" --sizes "1024" --gen 16 --repeats 1 --out (Join-Path $res "lcwarm-$Label.json") 2>&1 | Out-Null

python "$root\fnbench.py" --port $Port --label $Label --sizes $Sizes --gen $Gen `
  --repeats $Repeats --repeats-big $RepeatsBig --big-threshold $BigThreshold `
  --context-limit $Ctx --out (Join-Path $res "lc-$Label.json") 2>&1 | Tee-Object -FilePath (Join-Path $res "lc-$Label.log")

Get-Process llama-server -ErrorAction SilentlyContinue | Stop-Process -Force
Start-Sleep -Seconds 3

Write-Output ''
Write-Output "=== [$Label] summary (median of reps > 0) ==="
$j = Get-Content (Join-Path $res "lc-$Label.json") -Raw | ConvertFrom-Json
foreach ($grp in ($j.rows | Where-Object { -not $_.error } | Group-Object target_n)) {
  $pf = ($grp.Group | Where-Object { $_.rep -gt 0 } | ForEach-Object { $_.prefill_tps }) | Sort-Object
  $dc = ($grp.Group | Where-Object { $_.rep -gt 0 } | ForEach-Object { $_.decode_tps }) | Sort-Object
  if ($pf.Count -eq 0) { continue }
  $pmed = $pf[[int]($pf.Count/2)]; $dmed = $dc[[int]($dc.Count/2)]
  $acc = $grp.Group[-1].draft_n_accepted; $dn = $grp.Group[-1].draft_n
  $accStr = if ($dn) { "acc={0:P1}" -f ($acc / $dn) } else { "" }
  Write-Output ("  n={0,7} prefill={1,7:N1} t/s  decode={2,6:N2} t/s  {3}" -f [int]$grp.Name, $pmed, $dmed, $accStr)
}
Write-Output 'done'
