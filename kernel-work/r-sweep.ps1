# r-sweep.ps1 — pin the draft/target step-cost ratio r with high repeats.
# Three configs on the SAME trunk: no-MTP (baseline t), n-max 1, n-max 2.
# r falls out of decode_tps ratios + measured acceptance:
#   S_k = (1 + A_k) / (k*r + 1),  S_0 = 1  =>  r = ((1+A_k)/S_k - 1)/k
param(
  [int]$Ctx = 32768, [int]$B = 2048, [int]$Ub = 2048,
  [string]$Sizes = "1024,8192", [int]$Gen = 256, [int]$Repeats = 4, [int]$Port = 8273
)
$ErrorActionPreference = 'Continue'
$bin  = 'C:\AI\build\strix-llama-win\build-therock\bin\llama-server.exe'
$sdk  = 'C:\AI\sdk\therock1151'
$root = 'C:\Projects\REV-N-ornith-eval-20260911\kernel-work'
$res  = Join-Path $root 'results'
New-Item -ItemType Directory -Force -Path $res | Out-Null
$model = 'C:\AI\models\qwen38-flash\projfix\Qwen3.8-Flash-Next-IQ4_NL-PROJFIX-00001-of-00009.gguf'
$shared = 'C:\AI\models\qwen38-flash\projfix\mtp-Qwen3.8-Flash-Next-shared-Q8_0.gguf'
$blog = Join-Path $res 'r-sweep.summary.log'

$env:PATH = "$sdk\bin;$sdk\lib\llvm\bin;$env:PATH"
$env:ROCM_PATH = $sdk; $env:HIP_PATH = $sdk
$env:HIP_DEVICE_LIB_PATH = "$sdk\lib\llvm\amdgcn\bitcode"
$env:GGML_HIP_ENABLE_UNIFIED_MEMORY = '1'
$env:HSA_OVERRIDE_GFX_VERSION = '11.5.1'

$configs = @(
  @{ tag='r-none';   nmax=$null },
  @{ tag='r-nmax1';  nmax='1' },
  @{ tag='r-nmax2';  nmax='2' }
)

foreach ($c in $configs) {
  Get-Process llama-server -ErrorAction SilentlyContinue | Stop-Process -Force
  Start-Sleep -Seconds 5
  $a = @('-m',$model,'-dev','ROCm0','-ngl','999','-fa','on','-fit','off','--load-mode','none',
    '-ctk','f16','-ctv','f16','-c',"$Ctx",'-b',"$B",'-ub',"$Ub",'--parallel','1',
    '--host','127.0.0.1','--port',"$Port",'--no-webui')
  if ($c.nmax -ne $null) {
    $a += @('-md',$shared,'--spec-type','draft-mtp','--spec-draft-n-max',$c.nmax)
  }
  $sout = Join-Path $res "sm-$($c.tag).out"; $serr = Join-Path $res "sm-$($c.tag).err"
  "==== $($c.tag) n-max=$($c.nmax) $(Get-Date -Format o) ====" | Out-File $blog -Append -Encoding utf8
  $p = Start-Process -FilePath $bin -ArgumentList $a -PassThru -RedirectStandardOutput $sout -RedirectStandardError $serr -NoNewWindow
  $ok=$false; $t0=Get-Date
  while (((Get-Date)-$t0).TotalSeconds -lt 900) {
    if ($p.HasExited) { "  EXITED code=$($p.ExitCode)" | Out-File $blog -Append -Encoding utf8; break }
    try { if ((Invoke-WebRequest "http://127.0.0.1:$Port/health" -TimeoutSec 5 -UseBasicParsing).StatusCode -eq 200) { $ok=$true; break } } catch { Start-Sleep -Seconds 5 }
  }
  if ($ok) {
    "  READY $([int]((Get-Date)-$t0).TotalSeconds)s" | Out-File $blog -Append -Encoding utf8
    # warm the page cache: one throwaway pass before measuring
    python "$root\fnbench.py" --port $Port --label "$($c.tag)-warm" --sizes $Sizes --gen 64 --repeats 1 `
      --out (Join-Path $res "$($c.tag)-warm.json") 2>&1 | Out-Null
    python "$root\fnbench.py" --port $Port --label $($c.tag) --sizes $Sizes --gen $Gen --repeats $Repeats `
      --out (Join-Path $res "$($c.tag).json") 2>&1 | Tee-Object -FilePath $blog -Append
    $acc = Get-Content $serr | Select-String 'draft acceptance|accepted .*draft tokens' | ForEach-Object { $_.Line }
    foreach ($l in $acc) { "  ACC: $l" | Out-File $blog -Append -Encoding utf8 }
  } else { "  NOT READY" | Out-File $blog -Append -Encoding utf8 }
  Stop-Process -Id $p.Id -Force -ErrorAction SilentlyContinue
  Start-Sleep -Seconds 3
}
Get-Process llama-server -ErrorAction SilentlyContinue | Stop-Process -Force
"ALL DONE $(Get-Date -Format o)" | Out-File $blog -Append -Encoding utf8
