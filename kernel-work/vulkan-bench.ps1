# vulkan-bench.ps1 — start the Way-1 Windows/Vulkan server, benchmark, stop. One instance, ever.
# Usage example:
#   powershell -NoProfile -File vulkan-bench.ps1 -Tag v1-frspec-d3 -Sizes 1024,8192,32768,65536,131072
param(
  [string]$Tag = "v1-base",
  [string]$Model = "C:\AI\models\qwen38-flash\unsloth-UD-IQ4_XS\Qwen3.8-Flash-Next-UD-IQ4_XS-00001-of-00003.gguf",
  [string]$Draft = "C:\AI\models\qwen38-flash\drluoto-frspec\mtp-Qwen3.8-Flash-Next-Q8_0-frspec-65k.gguf",
  [int]$Ctx = 196608,
  [int]$Batch = 2048,
  [int]$Ubatch = 2048,
  [int]$DraftNMax = 3,
  [double]$DraftPMin = 0.0,
  [int]$Parallel = 1,
  [string]$Sizes = "1024,8192,32768,65536,131072",
  [int]$Gen = 128,
  [int]$Repeats = 3,
  [int]$RepeatsBig = 0,
  [int]$BigThreshold = 32768,
  [switch]$NoSpec,
  [string]$ExtraArgs = "",
  [int]$Port = 8113,
  [int]$LoadTimeoutSec = 1800
)
$ErrorActionPreference = "Continue"
$root = "C:\Projects\REV-N-ornith-eval-20260911\kernel-work"
$res  = Join-Path $root "results"
New-Item -ItemType Directory -Force -Path $res | Out-Null
$bin  = "C:\AI\runtimes\strix-vulkan-ba5354d\llama-server.exe"
$tpl  = "C:\AI\models\qwen38-flash\froggeric\chat_template.jinja"
$sout = Join-Path $res "server-$Tag.out"
$serr = Join-Path $res "server-$Tag.err"
$blog = Join-Path $res "bench-$Tag.log"

function Note($m) { $m | Tee-Object -FilePath $blog -Append }

# one-instance rule
Get-Process llama-server -ErrorAction SilentlyContinue | ForEach-Object { Note "killing stale llama-server pid $($_.Id)"; Stop-Process -Id $_.Id -Force }
Start-Sleep -Seconds 2

$argv = @(
  "-m", $Model,
  "-ngl", "999", "-fa", "on",
  "--host", "127.0.0.1", "--port", "$Port",
  "-c", "$Ctx", "--parallel", "$Parallel",
  "-ctk", "f16", "-ctv", "f16",
  "-b", "$Batch", "-ub", "$Ubatch",
  "--jinja", "--chat-template-file", $tpl,
  "--reasoning-format", "deepseek", "--reasoning-preserve",
  "--temp", "1.0", "--top-k", "20", "--top-p", "0.95", "--min-p", "0.0", "--presence-penalty", "0.0",
  "--alias", "qwen3.8-flash-next-mtp"
)
if (-not $NoSpec -and $Draft -ne "") {
  $argv += @("-md", $Draft, "--spec-type", "draft-mtp", "--spec-draft-n-max", "$DraftNMax", "--spec-draft-p-min", "$DraftPMin")
}
if ($ExtraArgs -ne "") { $argv += ($ExtraArgs -split '\s+') }

$env:GGML_VK_DISABLE_GDN_CACHE_FUSION = "1"
Note "=== starting $Tag $(Get-Date -Format o) ==="
Note "argv: $($argv -join ' ')"
$p = Start-Process -FilePath $bin -ArgumentList $argv -PassThru -RedirectStandardOutput $sout -RedirectStandardError $serr -NoNewWindow
Note "pid=$($p.Id) sout=$sout serr=$serr"

$ok = $false
$t0 = Get-Date
while (((Get-Date) - $t0).TotalSeconds -lt $LoadTimeoutSec) {
  if ($p.HasExited) { Note "SERVER EXITED code=$($p.ExitCode)"; Get-Content $serr -Tail 30; exit 1 }
  try {
    $r = Invoke-WebRequest -Uri "http://127.0.0.1:$Port/health" -TimeoutSec 5 -UseBasicParsing
    if ($r.StatusCode -eq 200) { $ok = $true; break }
  } catch { Start-Sleep -Seconds 5 }
}
if (-not $ok) { Note "SERVER NOT READY in $LoadTimeoutSec s"; Stop-Process -Id $p.Id -Force; exit 1 }
Note "server ready after $([int]((Get-Date)-$t0).TotalSeconds)s"

$out = Join-Path $res "$Tag.json"
python "$root\fnbench.py" --port $Port --label $Tag --sizes $Sizes --gen $Gen --repeats $Repeats --repeats-big $RepeatsBig --big-threshold $BigThreshold --out $out --context-limit $Ctx 2>&1 | Tee-Object -FilePath $blog -Append

Note "=== stopping $Tag $(Get-Date -Format o) ==="
Stop-Process -Id $p.Id -Force -ErrorAction SilentlyContinue
Start-Sleep -Seconds 3
Get-Process llama-server -ErrorAction SilentlyContinue | Stop-Process -Force
Note "done: $out"
