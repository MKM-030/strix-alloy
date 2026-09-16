# round-ledger.ps1 — capture the per-round speculation ledger via trace verbosity (-lv 4).
# The fork accumulates t_begin_us (refresh), t_draft_us (drafting), t_accept_us (accumulation) and
# prints them at LOG_LEVEL_TRACE with call counts, so per-call means are derivable without a rebuild.
param(
  [int]$Ctx = 16384, [int]$B = 2048, [int]$Ub = 2048,
  [int]$Prompt = 8192, [int]$Gen = 256, [int]$Port = 8277, [int]$Nmax = 2
)
$ErrorActionPreference = 'Continue'
$bin  = 'C:\AI\build\strix-llama-win\build-therock\bin\llama-server.exe'
$sdk  = 'C:\AI\sdk\therock1151'
$root = 'C:\Projects\REV-N-ornith-eval-20260911\kernel-work'
$res  = Join-Path $root 'results'
$model = 'C:\AI\models\qwen38-flash\projfix\Qwen3.8-Flash-Next-IQ4_NL-PROJFIX-00001-of-00009.gguf'
$head  = 'C:\AI\models\qwen38-flash\projfix\mtp-Qwen3.8-Flash-Next-shared-Q8_0.gguf'

Get-Process llama-server -ErrorAction SilentlyContinue | Stop-Process -Force
Start-Sleep -Seconds 3
$env:PATH = "$sdk\bin;$sdk\lib\llvm\bin;$env:PATH"
$env:ROCM_PATH = $sdk; $env:HIP_PATH = $sdk
$env:HIP_DEVICE_LIB_PATH = "$sdk\lib\llvm\amdgcn\bitcode"
$env:HSA_OVERRIDE_GFX_VERSION = '11.5.1'

$a = @('-m',$model,'-md',$head,'-dev','ROCm0','-ngl','999','-fa','on','-fit','off','--load-mode','none',
  '-ctk','f16','-ctv','f16','-c',"$Ctx",'-b',"$B",'-ub',"$Ub",'--parallel','1',
  '--host','127.0.0.1','--port',"$Port",'--no-webui','-lv','4',
  '--spec-type','draft-mtp','--spec-draft-n-max',"$Nmax")
$serr = Join-Path $res 'rl-server.err'; $sout = Join-Path $res 'rl-server.out'
$p = Start-Process -FilePath $bin -ArgumentList $a -PassThru -RedirectStandardOutput $sout -RedirectStandardError $serr -NoNewWindow
$ok=$false; $t0=Get-Date
while (((Get-Date)-$t0).TotalSeconds -lt 900) {
  if ($p.HasExited) { "EXITED $($p.ExitCode)"; break }
  try { if ((Invoke-WebRequest "http://127.0.0.1:$Port/health" -TimeoutSec 5 -UseBasicParsing).StatusCode -eq 200) { $ok=$true; break } } catch { Start-Sleep -Seconds 5 }
}
if (-not $ok) { "NOT READY"; exit 1 }
"READY $([int]((Get-Date)-$t0).TotalSeconds)s"

python "$root\fnbench.py" --port $Port --label "rl-n$Nmax-warm" --sizes "$Prompt" --gen 64 --repeats 1 `
  --out (Join-Path $res "rl-n$Nmax-warm.json") 2>&1 | Select-String -Pattern 'decode|n='
python "$root\fnbench.py" --port $Port --label "rl-n$Nmax" --sizes "$Prompt" --gen $Gen --repeats 1 `
  --out (Join-Path $res "rl-n$Nmax.json") 2>&1 | Select-String -Pattern 'decode|prefill|n='

Start-Sleep -Seconds 2
Get-Process llama-server -ErrorAction SilentlyContinue | Stop-Process -Force
Start-Sleep -Seconds 2

"=== ledger lines ==="
Get-Content $serr | Select-String -Pattern 'statistics draft-mtp|dur\(b,g,a\)|draft acceptance|graphs reused|phase: tgt_decode' |
  ForEach-Object { $_.Line }
