#requires -Version 5.1
# decode-baseline.ps1 — low-variance SERIAL decode baseline for kernel A/B (no MTP).
#
# Kernel changes affect the TARGET forward pass. MTP mixes draft+verify and acceptance into the
# wall time, which adds variance; so for kernel A/B we measure SERIAL decode (no drafter), where
# decode_tps is purely the target's cost per token. We take many reps at a fixed depth and report
# median + spread so a small kernel delta is distinguishable from noise.
param(
  [int]$Ctx = 32768,
  [int]$Port = 8320,
  [int]$Gen = 256,
  [int]$Repeats = 5,
  [string]$Sizes = "8192",
  [string]$Label = "baseline",
  [string]$OutDir = "results",
  [switch]$SmallK
)
$ErrorActionPreference = 'Continue'
$bin  = 'C:\AI\build\strix-llama-win\build-therock\bin\llama-server.exe'
$sdk  = 'C:\AI\sdk\therock1151'
$root = 'C:\Projects\REV-N-ornith-eval-20260911\kernel-work'
$res  = Join-Path $root $OutDir
$model = 'C:\AI\models\qwen38-flash\projfix\Qwen3.8-Flash-Next-IQ4_NL-PROJFIX-00001-of-00009.gguf'

$env:PATH = "$sdk\bin;$sdk\lib\llvm\bin;$env:PATH"
$env:ROCM_PATH = $sdk; $env:HIP_PATH = $sdk
$env:HIP_DEVICE_LIB_PATH = "$sdk\lib\llvm\amdgcn\bitcode"
$env:HSA_OVERRIDE_GFX_VERSION = '11.5.1'
# arm switch: enable the RDNA3.5 small-K MMVQ path (patch in mmvq.cu) for this run
if ($SmallK) { $env:GGML_MMVQ_RDNA35_SMALLK = '1'; Write-Output "[$Label] SMALLK enabled" }
else { Remove-Item Env:GGML_MMVQ_RDNA35_SMALLK -ErrorAction SilentlyContinue; Write-Output "[$Label] SMALLK off (upstream)" }

Get-Process llama-server -ErrorAction SilentlyContinue | Stop-Process -Force
Start-Sleep -Seconds 5
$a = @('-m',$model,'-dev','ROCm0','-ngl','999','-fa','on','-fit','off','--load-mode','none',
  '-ctk','f16','-ctv','f16','-c',"$Ctx",'-b','2048','-ub','2048','--parallel','1',
  '--host','127.0.0.1','--port',"$Port",'--no-webui','--seed','1234')
$serr = Join-Path $res "dbl-$Label.err"; $sout = Join-Path $res "dbl-$Label.out"
Remove-Item $serr,$sout -ErrorAction SilentlyContinue
$p = Start-Process -FilePath $bin -ArgumentList $a -PassThru -RedirectStandardOutput $sout -RedirectStandardError $serr -NoNewWindow
$ok=$false; $t0=Get-Date
while (((Get-Date)-$t0).TotalSeconds -lt 420) {
  if ($p.HasExited) { Write-Output "EXITED $($p.ExitCode)"; Get-Content $serr -Tail 10; return }
  try { if ((Invoke-WebRequest "http://127.0.0.1:$Port/health" -TimeoutSec 5 -UseBasicParsing).StatusCode -eq 200) { $ok=$true; break } } catch { Start-Sleep -Seconds 4 }
}
if (-not $ok) { Write-Output 'NOT READY'; Get-Content $serr -Tail 10; return }
Write-Output "[$Label] ready $([int]((Get-Date)-$t0).TotalSeconds)s"
# warm
python "$root\fnbench.py" --port $Port --label "dbl-warm-$Label" --sizes "1024" --gen 16 --repeats 1 --out (Join-Path $res "dbl-warm-$Label.json") 2>&1 | Out-Null
python "$root\fnbench.py" --port $Port --label $Label --sizes $Sizes --gen $Gen --repeats $Repeats --out (Join-Path $res "dbl-$Label.json") 2>&1 | Tee-Object -FilePath (Join-Path $res "dbl-$Label.log")
Get-Process llama-server -ErrorAction SilentlyContinue | Stop-Process -Force
Start-Sleep -Seconds 3

# summarize: median decode tps and ms/token, excluding rep 0 (cold)
$j = Get-Content (Join-Path $res "dbl-$Label.json") -Raw | ConvertFrom-Json
foreach ($grp in ($j.rows | Where-Object { -not $_.error } | Group-Object target_n)) {
  $vals = ($grp.Group | Where-Object { $_.rep -gt 0 } | ForEach-Object { $_.decode_tps }) | Sort-Object
  if ($vals.Count -eq 0) { $vals = ($grp.Group | ForEach-Object { $_.decode_tps }) | Sort-Object }
  $med = $vals[[int]($vals.Count/2)]
  $mn = $vals[0]; $mx = $vals[-1]
  $msPerTok = 1000.0 / $med
  Write-Output ("[$Label] n=$($grp.Name) reps=$($vals.Count) decode median={0:N2} t/s [{1:N2}..{2:N2}]  ms/token={3:N3}" -f $med,$mn,$mx,$msPerTok)
}
