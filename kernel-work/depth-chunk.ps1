#requires -Version 5.1
# depth-chunk.ps1 — Codex Step 2b: cost of a FIXED appended chunk at increasing occupied depth.
#
# Holds -c fixed (so capacity is constant) and varies only how much history is actually occupied.
# This separates "allocation cost" from "real history-processing cost" — the two halves of the
# configured-context penalty question.
#
# WSL must be down. No drafter (keeps the hidden-state/output contract fixed).
param(
  [int]$Ctx = 262144,
  [int]$Port = 8381,
  [string]$Depths = "0,32768,65536,131072,200704",
  [int]$Chunk = 8192,
  [int]$Repeats = 2,
  [int]$Ub = 16384,
  [string]$Label = "depth-chunk"
)
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

Get-Process llama-server -ErrorAction SilentlyContinue | Stop-Process -Force
Start-Sleep -Seconds 5
$a = @('-m',$model,'-dev','ROCm0','-ngl','999','-fa','on','-fit','off','--load-mode','none',
  '-ctk','f16','-ctv','f16','-c',"$Ctx",'-b',"$Ub",'-ub',"$Ub",'--parallel','1',
  '--host','127.0.0.1','--port',"$Port",'--no-webui','--seed','1234')
$serr = Join-Path $res "dch-$Label.err"
Remove-Item $serr -ErrorAction SilentlyContinue
$p = Start-Process -FilePath $bin -ArgumentList $a -PassThru -RedirectStandardOutput (Join-Path $res "dch-$Label.out") -RedirectStandardError $serr -NoNewWindow
$ok=$false; $t0=Get-Date
while (((Get-Date)-$t0).TotalSeconds -lt 600) {
  if ($p.HasExited) { Write-Output "EXITED $($p.ExitCode)"; Get-Content $serr -Tail 8; return }
  try { if ((Invoke-WebRequest "http://127.0.0.1:$Port/health" -TimeoutSec 5 -UseBasicParsing).StatusCode -eq 200) { $ok=$true; break } } catch { Start-Sleep -Seconds 5 }
}
if (-not $ok) { Write-Output 'NOT READY'; Get-Content $serr -Tail 8; return }
Write-Output "[$Label] ready (-c $Ctx, ub $Ub, chunk $Chunk)"

python "$root\chunk-depth-bench.py" --port $Port --depths $Depths --chunk $Chunk --repeats $Repeats `
  --label $Label --out (Join-Path $res "dch-$Label.json") 2>&1 | Tee-Object -FilePath (Join-Path $res "dch-$Label.log")

Get-Process llama-server -ErrorAction SilentlyContinue | Stop-Process -Force
Start-Sleep -Seconds 3

Write-Output ''
Write-Output "=== [$Label] chunk prefill vs occupied depth (median of reps) ==="
$j = Get-Content (Join-Path $res "dch-$Label.json") -Raw | ConvertFrom-Json
foreach ($g in ($j.rows | Group-Object depth)) {
  $v = ($g.Group | ForEach-Object { $_.chunk_tps } | Where-Object { $_ -ne $null }) | Sort-Object
  if ($v.Count -eq 0) { continue }
  $med = $v[[int]($v.Count/2)]
  $proc = ($g.Group | Select-Object -First 1).processed_tokens
  Write-Output ("  depth {0,7}: chunk {1:N1} t/s   (processed {2} tok, n={3})" -f [int]$g.Name, $med, $proc, $v.Count)
}
Write-Output 'done'
