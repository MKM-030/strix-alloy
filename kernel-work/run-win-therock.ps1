# run-win-therock.ps1 — run the TheRock (clang 24) build and benchmark it.
param(
  [string]$Tag = "therock-base",
  [Parameter(Mandatory=$true)][string]$Model,
  [int]$Ctx = 49152, [int]$B = 2048, [int]$Ub = 2048,
  [string]$Sizes = "1024,8192,16384,32768", [int]$Gen = 256, [int]$Repeats = 3,
  [string]$Mtp = "", [int]$Port = 8270, [string]$ExtraArgs = ""
)
$ErrorActionPreference = 'Continue'
$bin  = 'C:\AI\build\strix-llama-win\build-therock\bin\llama-server.exe'
$sdk  = 'C:\AI\sdk\therock1151'
$root = 'C:\Projects\REV-N-ornith-eval-20260911\kernel-work'
$res  = Join-Path $root 'results'
New-Item -ItemType Directory -Force -Path $res | Out-Null

Get-Process llama-server -ErrorAction SilentlyContinue | ForEach-Object { Stop-Process -Id $_.Id -Force }
Start-Sleep -Seconds 3
$env:PATH = "$sdk\bin;$sdk\lib\llvm\bin;$env:PATH"
$env:ROCM_PATH = $sdk; $env:HIP_PATH = $sdk
$env:HIP_DEVICE_LIB_PATH = "$sdk\lib\llvm\amdgcn\bitcode"
$env:GGML_HIP_ENABLE_UNIFIED_MEMORY = '1'
$env:HSA_OVERRIDE_GFX_VERSION = '11.5.1'

$a = @('-m',$Model,'-dev','ROCm0','-ngl','999','-fa','on','-fit','off','--load-mode','none',
  '-ctk','f16','-ctv','f16','-c',"$Ctx",'-b',"$B",'-ub',"$Ub",'--parallel','1',
  '--host','127.0.0.1','--port',"$Port",'--no-webui')
if ($Mtp -ne "") { $a += @('-md',$Mtp,'--spec-type','draft-mtp','--spec-draft-n-max','2') }

$sout = Join-Path $res "tr-$Tag.out"; $serr = Join-Path $res "tr-$Tag.err"; $blog = Join-Path $res "trb-$Tag.log"
function Note($m) { $m | Tee-Object -FilePath $blog -Append }
Note "==== $Tag $(Get-Date -Format o) ===="
Note "bin: $bin"
Note "argv: $($a -join ' ')"
$p = Start-Process -FilePath $bin -ArgumentList $a -PassThru -RedirectStandardOutput $sout -RedirectStandardError $serr -NoNewWindow
Note "pid=$($p.Id)"
$ok=$false; $t0=Get-Date
while (((Get-Date)-$t0).TotalSeconds -lt 1800) {
  if ($p.HasExited) { Note "EXITED code=$($p.ExitCode)"; Get-Content $serr -Tail 12; exit 1 }
  try { if ((Invoke-WebRequest "http://127.0.0.1:$Port/health" -TimeoutSec 5 -UseBasicParsing).StatusCode -eq 200) { $ok=$true; break } } catch { Start-Sleep -Seconds 5 }
}
if (-not $ok) { Note "NOT READY"; Stop-Process -Id $p.Id -Force; exit 1 }
Note ("ready after " + [int]((Get-Date)-$t0).TotalSeconds + "s")
python "$root\fnbench.py" --port $Port --label $Tag --sizes $Sizes --gen $Gen --repeats $Repeats `
  --out (Join-Path $res "$Tag.json") 2>&1 | Tee-Object -FilePath $blog -Append
Note "stopping"
Stop-Process -Id $p.Id -Force -ErrorAction SilentlyContinue
Start-Sleep -Seconds 3
Get-Process llama-server -ErrorAction SilentlyContinue | Stop-Process -Force
Note "done"
