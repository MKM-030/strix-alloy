#requires -Version 5.1
# capacity-prefill.ps1 — does allocating KV capacity cost throughput before that capacity is occupied?
#
# Codex's Step 2a. FIXED: exact same 16k prompt, zero starting depth, same -b/-ub, same outputs,
# NO drafter. CHANGED: only -c. Warm reps (rep 0 discarded). WSL must be down.
#
# This isolates "configured capacity" from "occupied depth". If prefill t/s falls purely as -c rises,
# the penalty is allocation/placement (or per-slot work over unused capacity). If it does not, the
# earlier 862-vs-1021 gap was something else.
param(
  [string]$Cs = "32768,65536,131072,262144",
  [int]$Size = 16384,
  [int]$Gen = 64,
  [int]$Repeats = 2,
  [int]$Ub = 16384,
  [int]$Port = 8380
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

# KV bytes per token: 12 full-attn layers * (K,V) * 2 kv-heads * 256 dim * 2 bytes = 24576 B/token
$KV_PER_TOKEN = 24576

$out = @()
foreach ($c in ($Cs.Split(',') | ForEach-Object { [int]$_.Trim() })) {
  Get-Process llama-server -ErrorAction SilentlyContinue | Stop-Process -Force
  Start-Sleep -Seconds 5
  $a = @('-m',$model,'-dev','ROCm0','-ngl','999','-fa','on','-fit','off','--load-mode','none',
    '-ctk','f16','-ctv','f16','-c',"$c",'-b',"$Ub",'-ub',"$Ub",'--parallel','1',
    '--host','127.0.0.1','--port',"$Port",'--no-webui','--seed','1234')
  $serr = Join-Path $res "cap-$c.err"
  Remove-Item $serr -ErrorAction SilentlyContinue
  $p = Start-Process -FilePath $bin -ArgumentList $a -PassThru -RedirectStandardOutput (Join-Path $res "cap-$c.out") -RedirectStandardError $serr -NoNewWindow
  $ok=$false; $t0=Get-Date
  while (((Get-Date)-$t0).TotalSeconds -lt 600) {
    if ($p.HasExited) { Write-Output "[c=$c] EXITED $($p.ExitCode)"; Get-Content $serr -Tail 8; break }
    try { if ((Invoke-WebRequest "http://127.0.0.1:$Port/health" -TimeoutSec 5 -UseBasicParsing).StatusCode -eq 200) { $ok=$true; break } } catch { Start-Sleep -Seconds 5 }
  }
  if (-not $ok) { Write-Output "[c=$c] NOT READY"; continue }
  Write-Output "[c=$c] ready; KV alloc = $([math]::Round($c*$KV_PER_TOKEN/1GB,2)) GiB"
  # warm the page cache with a small request first, then the real ladder
  python "$root\fnbench.py" --port $Port --label "capwarm-$c" --sizes "1024" --gen 16 --repeats 1 --out (Join-Path $res "capwarm-$c.json") 2>&1 | Out-Null
  python "$root\fnbench.py" --port $Port --label "cap-$c" --sizes "$Size" --gen $Gen --repeats $Repeats --out (Join-Path $res "cap-$c.json") 2>&1 | Tee-Object -FilePath (Join-Path $res "cap-$c.log")
  Get-Process llama-server -ErrorAction SilentlyContinue | Stop-Process -Force
  Start-Sleep -Seconds 3

  $j = Get-Content (Join-Path $res "cap-$c.json") -Raw -ErrorAction SilentlyContinue | ConvertFrom-Json
  $warm = ($j.rows | Where-Object { $_.rep -gt 0 -and -not $_.error })
  if ($warm.Count -eq 0) { Write-Output "[c=$c] no warm rows"; continue }
  $pf = ($warm | ForEach-Object { $_.prefill_tps }) | Sort-Object
  $dc = ($warm | ForEach-Object { $_.decode_tps }) | Sort-Object
  $pmed = $pf[[int]($pf.Count/2)]; $dmed = $dc[[int]($dc.Count/2)]
  $msPerTok = 1000.0/$dmed
  # effective weight-payload bandwidth for serial decode = 4.219 GB / ms
  $effBw = 4.219/$msPerTok*1000
  $out += [pscustomobject]@{ c=$c; kv_gib=[math]::Round($c*$KV_PER_TOKEN/1GB,2); prefill_tps=[math]::Round($pmed,1); decode_tps=[math]::Round($dmed,2); eff_bw_gbs=[math]::Round($effBw,1) }
  Write-Output ("  [c={0}] prefill={1:N1} t/s  decode={2:N2} t/s  eff-bw(4.219GB)={3:N1} GB/s" -f $c,$pmed,$dmed,$effBw)
  Write-Output ''
}
$out | ConvertTo-Json -Depth 4 | Set-Content (Join-Path $res 'capacity-prefill.json')
Write-Output '=== capacity summary (prompt 16384, no drafter, warm) ==='
$out | ForEach-Object { Write-Output ("  -c {0,6}  KV {1,5} GiB  prefill {2,7:N1} t/s  decode {3,6:N2} t/s  eff-bw {4,5:N1} GB/s" -f $_.c,$_.kv_gib,$_.prefill_tps,$_.decode_tps,$_.eff_bw_gbs) }
$base = ($out | Where-Object { $_.c -eq 32768 } | Select-Object -First 1)
if ($base) {
  foreach ($r in $out) { Write-Output ("  -c {0,6}: prefill {1,6:N1}% of -c 32768" -f $r.c, (100*$r.prefill_tps/$base.prefill_tps)) }
}
Write-Output 'done'
