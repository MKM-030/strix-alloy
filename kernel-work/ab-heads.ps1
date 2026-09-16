# ab-heads.ps1 — clean A/B: shared Q8_0 MTP head vs FR-Spec 65k trimmed head.
# Same trunk (PROJFIX), same ctx/b/ub, same gen, same n-max per pair. Serial (one server at a time).
# Answers: does the 3.8x-smaller draft projection (output.weight 65536 vs 248320 rows) raise decode t/s?
param(
  [int]$Ctx = 32768, [int]$B = 2048, [int]$Ub = 2048,
  [string]$Sizes = "1024,8192,16384", [int]$Gen = 256, [int]$Repeats = 2,
  [string]$Nmax = "1,2", [int]$Port = 8272
)
$ErrorActionPreference = 'Continue'
$bin  = 'C:\AI\build\strix-llama-win\build-therock\bin\llama-server.exe'
$sdk  = 'C:\AI\sdk\therock1151'
$root = 'C:\Projects\REV-N-ornith-eval-20260911\kernel-work'
$res  = Join-Path $root 'results'
New-Item -ItemType Directory -Force -Path $res | Out-Null

$model  = 'C:\AI\models\qwen38-flash\projfix\Qwen3.8-Flash-Next-IQ4_NL-PROJFIX-00001-of-00009.gguf'
$heads  = [ordered]@{
  shared = 'C:\AI\models\qwen38-flash\projfix\mtp-Qwen3.8-Flash-Next-shared-Q8_0.gguf'
  frspec = 'C:\AI\models\qwen38-flash\projfix\mtp-frspec-65k-pwhead.gguf'
}
$blog = Join-Path $res 'ab-heads.summary.log'

$env:PATH = "$sdk\bin;$sdk\lib\llvm\bin;$env:PATH"
$env:ROCM_PATH = $sdk; $env:HIP_PATH = $sdk
$env:HIP_DEVICE_LIB_PATH = "$sdk\lib\llvm\amdgcn\bitcode"
$env:HSA_OVERRIDE_GFX_VERSION = '11.5.1'

foreach ($nmax in $Nmax.Split(',')) {
  foreach ($hn in $heads.Keys) {
    $tag = "ab-$hn-n$nmax"
    Get-Process llama-server -ErrorAction SilentlyContinue | Stop-Process -Force
    Start-Sleep -Seconds 5
    $a = @('-m',$model,'-dev','ROCm0','-ngl','999','-fa','on','-fit','off','--load-mode','none',
      '-ctk','f16','-ctv','f16','-c',"$Ctx",'-b',"$B",'-ub',"$Ub",'--parallel','1',
      '--host','127.0.0.1','--port',"$Port",'--no-webui',
      '-md',$heads[$hn],'--spec-type','draft-mtp','--spec-draft-n-max',$nmax)
    $sout = Join-Path $res "sm-$tag.out"; $serr = Join-Path $res "sm-$tag.err"
    "==== $tag n-max=$nmax head=$($heads[$hn]) $(Get-Date -Format o) ====" | Out-File $blog -Append -Encoding utf8
    $p = Start-Process -FilePath $bin -ArgumentList $a -PassThru -RedirectStandardOutput $sout -RedirectStandardError $serr -NoNewWindow
    $ok=$false; $t0=Get-Date
    while (((Get-Date)-$t0).TotalSeconds -lt 900) {
      if ($p.HasExited) { "  EXITED code=$($p.ExitCode)" | Out-File $blog -Append -Encoding utf8; break }
      try { if ((Invoke-WebRequest "http://127.0.0.1:$Port/health" -TimeoutSec 5 -UseBasicParsing).StatusCode -eq 200) { $ok=$true; break } } catch { Start-Sleep -Seconds 5 }
    }
    if ($ok) {
      "  READY $([int]((Get-Date)-$t0).TotalSeconds)s" | Out-File $blog -Append -Encoding utf8
      python "$root\fnbench.py" --port $Port --label $tag --sizes $Sizes --gen $Gen --repeats $Repeats `
        --out (Join-Path $res "$tag.json") 2>&1 | Tee-Object -FilePath $blog -Append
      $acc = Get-Content $serr | Select-String 'draft acceptance' | ForEach-Object { $_.Line }
      foreach ($l in $acc) { "  ACC: $l" | Out-File $blog -Append -Encoding utf8 }
    } else { "  NOT READY" | Out-File $blog -Append -Encoding utf8 }
    Stop-Process -Id $p.Id -Force -ErrorAction SilentlyContinue
    Start-Sleep -Seconds 3
  }
}
Get-Process llama-server -ErrorAction SilentlyContinue | Stop-Process -Force
"ALL DONE $(Get-Date -Format o)" | Out-File $blog -Append -Encoding utf8
