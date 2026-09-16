# run-win-hip.ps1 — run the native Windows HIP llama-server and benchmark it.
# usage: run-win-hip.ps1 -Tag win-ud-gates -Model <path> -Ctx 49152 -B 8192 -Ub 8192 -Sizes "1024,8192,32768" -Gen 256 [-Mtp <head>]
param(
  [string]$Tag = "win-hip-base",
  [Parameter(Mandatory=$true)][string]$Model,
  [int]$Ctx = 49152,
  [int]$B = 8192,
  [int]$Ub = 8192,
  [string]$Sizes = "1024,8192,32768",
  [int]$Gen = 256,
  [int]$Repeats = 3,
  [string]$Mtp = "",
  [int]$Port = 8180
)
$ErrorActionPreference = 'Continue'
$bin    = 'C:\AI\build\strix-llama-win\build-win\bin\llama-server.exe'
$rocm   = 'C:\Program Files\AMD\ROCm\7.2'
$root   = 'C:\Projects\REV-N-ornith-eval-20260911\kernel-work'
$res    = Join-Path $root 'results'
New-Item -ItemType Directory -Force -Path $res | Out-Null

Get-Process llama-server -ErrorAction SilentlyContinue | ForEach-Object { Write-Output "killing stale $($_.Id)"; Stop-Process -Id $_.Id -Force }
Start-Sleep -Seconds 2

# Prepend ROCm to the existing PATH (do NOT replace it: python/curl live outside System32)
$env:PATH = "$rocm\bin;$rocm\lib\llvm\bin;$env:PATH"
$env:ROCM_PATH = $rocm
$env:HIP_PATH = $rocm
$env:GGML_HIP_ENABLE_UNIFIED_MEMORY = "1"
$env:HSA_OVERRIDE_GFX_VERSION = "11.5.1"

$argv = @(
  "-m", $Model, "-dev", "ROCm0", "-ngl", "999", "-fa", "on", "-fit", "off",
  "--load-mode", "none", "-ctk", "f16", "-ctv", "f16",
  "-c", "$Ctx", "-b", "$B", "-ub", "$Ub", "--parallel", "1",
  "--host", "127.0.0.1", "--port", "$Port", "--no-webui"
)
if ($Mtp -ne "") { $argv += @("-md", $Mtp, "--spec-type", "draft-mtp", "--spec-draft-n-max", "2") }

$sout = Join-Path $res "wins-$Tag.out"
$serr = Join-Path $res "wins-$Tag.err"
$blog = Join-Path $res "winb-$Tag.log"
function Note($m) { $m | Tee-Object -FilePath $blog -Append }

Note "==== $Tag $(Get-Date -Format o) ===="
Note "bin: $bin"
Note "argv: $($argv -join ' ')"
$p = Start-Process -FilePath $bin -ArgumentList $argv -PassThru -RedirectStandardOutput $sout -RedirectStandardError $serr -NoNewWindow
Note "pid=$($p.Id)"

$ok = $false; $t0 = Get-Date
while (((Get-Date) - $t0).TotalSeconds -lt 1800) {
  if ($p.HasExited) { Note "SERVER EXITED code=$($p.ExitCode)"; Get-Content $serr -Tail 25; exit 1 }
  try { $r = Invoke-WebRequest -Uri "http://127.0.0.1:$Port/health" -TimeoutSec 5 -UseBasicParsing
        if ($r.StatusCode -eq 200) { $ok = $true; break } } catch { Start-Sleep -Seconds 5 }
}
if (-not $ok) { Note "NOT READY"; Stop-Process -Id $p.Id -Force; exit 1 }
Note "ready after $([int]((Get-Date)-$t0).TotalSeconds)s"

$out = Join-Path $res "$Tag.json"
python "$root\fnbench.py" --port $Port --label $Tag --sizes $Sizes --gen $Gen --repeats $Repeats `
  --out $out 2>&1 | Tee-Object -FilePath $blog -Append
Note "fnbench exit=$LASTEXITCODE"

Note "stopping"
Stop-Process -Id $p.Id -Force -ErrorAction SilentlyContinue
Start-Sleep -Seconds 3
Get-Process llama-server -ErrorAction SilentlyContinue | Stop-Process -Force
Note "done: $out (exe=$bin)"
