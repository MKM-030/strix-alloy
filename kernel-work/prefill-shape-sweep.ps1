#requires -Version 5.1
# prefill-shape-sweep.ps1 — prefill t/s vs prompt depth with the max-prefill shape (ub 16384, no drafter).
# Purpose: the published "gap" (ilintar 1204) is quoted at ~0 depth; our 1057 is at 16k. Depth is the
# dominant variable for prefill t/s, so compare at MATCHED depth before concluding there is a gap.
param([int]$Ctx = 32768, [int]$Port = 8330, [int]$Gen = 16, [int]$Repeats = 3,
      [string]$Sizes = "128,256,512,1024,2048,4096,8192", [string]$Label = "prefill-ub16384",
      [int]$MinT = 0, [int]$Ub = 16384)
$ErrorActionPreference = 'Continue'
$bin  = 'C:\AI\build\strix-llama-win\build-therock\bin\llama-server.exe'
$sdk  = 'C:\AI\sdk\therock1151'
$root = 'C:\Projects\REV-N-ornith-eval-20260911\kernel-work'
$res  = Join-Path $root 'results'
$model = 'C:\AI\models\qwen38-flash\projfix\Qwen3.8-Flash-Next-IQ4_NL-PROJFIX-00001-of-00009.gguf'

$env:PATH = "$sdk\bin;$sdk\lib\llvm\bin;$env:PATH"
$env:ROCM_PATH = $sdk; $env:HIP_PATH = $sdk
$env:HIP_DEVICE_LIB_PATH = "$sdk\lib\llvm\amdgcn\bitcode"
$env:GGML_HIP_ENABLE_UNIFIED_MEMORY = '1'
$env:HSA_OVERRIDE_GFX_VERSION = '11.5.1'
if ($MinT -gt 0) { $env:GGML_MMB_MIN_T = "$MinT"; Write-Output "[$Label] GGML_MMB_MIN_T=$MinT" }
else { Remove-Item Env:GGML_MMB_MIN_T -ErrorAction SilentlyContinue; Write-Output "[$Label] GGML_MMB_MIN_T unset (512)" }

Get-Process llama-server -ErrorAction SilentlyContinue | Stop-Process -Force
Start-Sleep -Seconds 5
$a = @('-m',$model,'-dev','ROCm0','-ngl','999','-fa','on','-fit','off','--load-mode','none',
  '-ctk','f16','-ctv','f16','-c',"$Ctx",'-b',"$Ub",'-ub',"$Ub",'--parallel','1',
  '--host','127.0.0.1','--port',"$Port",'--no-webui','--seed','1234')
$serr = Join-Path $res "pfs-$Label.err"
$p = Start-Process -FilePath $bin -ArgumentList $a -PassThru -RedirectStandardOutput (Join-Path $res "pfs-$Label.out") -RedirectStandardError $serr -NoNewWindow
$ok=$false; $t0=Get-Date
while (((Get-Date)-$t0).TotalSeconds -lt 420) {
  if ($p.HasExited) { Write-Output "EXITED $($p.ExitCode)"; Get-Content $serr -Tail 8; return }
  try { if ((Invoke-WebRequest "http://127.0.0.1:$Port/health" -TimeoutSec 5 -UseBasicParsing).StatusCode -eq 200) { $ok=$true; break } } catch { Start-Sleep -Seconds 4 }
}
if (-not $ok) { Write-Output 'NOT READY'; Get-Content $serr -Tail 8; return }
Write-Output "[$Label] ready"
python "$root\fnbench.py" --port $Port --label "pfs-warm" --sizes "1024" --gen 16 --repeats 1 --out (Join-Path $res "pfs-warm.json") 2>&1 | Out-Null
python "$root\fnbench.py" --port $Port --label $Label --sizes $Sizes --gen $Gen --repeats $Repeats --out (Join-Path $res "pfs-$Label.json") 2>&1 | Tee-Object -FilePath (Join-Path $res "pfs-$Label.log")
Get-Process llama-server -ErrorAction SilentlyContinue | Stop-Process -Force
Start-Sleep -Seconds 3
$j = Get-Content (Join-Path $res "pfs-$Label.json") -Raw | ConvertFrom-Json
foreach ($grp in ($j.rows | Where-Object { -not $_.error } | Group-Object target_n)) {
  $vals = ($grp.Group | Where-Object { $_.rep -gt 0 } | ForEach-Object { $_.prefill_tps }) | Sort-Object
  if ($vals.Count -eq 0) { continue }
  $med = $vals[[int]($vals.Count/2)]
  Write-Output ("[$Label] prompt_n=$($grp.Name) prefill median={0:N1} t/s" -f $med)
}
