#requires -Version 5.1
# reproduce-b1-bugA.ps1 — the handover's "shared-MTP / large-ubatch load failure" (prior work: Bug A).
#
# Prior work (docs/benchmarks/native-windows-hip-build-and-qualification-20260914.md, section 3b)
# isolated Bug A as: `-b/-ub 8192` + a draft model -> llama_model_load dies with
# "invalid vector subscript", independent of the context and of whether the head is shared.
# This script re-confirms that on the CURRENT binary and adds the fit-probe variant (B1-fit) that
# fails earlier with "qwen4exp requires ctx_other to be set".
#
# Each row is a single launch; we record reach-/health, exit code, and the first fatal line.
param([int]$Port = 8303)
$ErrorActionPreference = 'Continue'
$bin  = 'C:\AI\build\strix-llama-win\build-therock\bin\llama-server.exe'
$sdk  = 'C:\AI\sdk\therock1151'
$root = 'C:\Projects\REV-N-ornith-eval-20260911\kernel-work'
$res  = Join-Path $root 'results'
$model = 'C:\AI\models\qwen38-flash\projfix\Qwen3.8-Flash-Next-IQ4_NL-PROJFIX-00001-of-00009.gguf'
$head  = 'C:\AI\models\qwen38-flash\projfix\mtp-Qwen3.8-Flash-Next-shared-Q8_0.gguf'

$env:PATH = "$sdk\bin;$sdk\lib\llvm\bin;$env:PATH"
$env:ROCM_PATH = $sdk; $env:HIP_PATH = $sdk
$env:HIP_DEVICE_LIB_PATH = "$sdk\lib\llvm\amdgcn\bitcode"
$env:HSA_OVERRIDE_GFX_VERSION = '11.5.1'

function Try-One([string]$tag, [int]$ctx, [int]$bub, [bool]$draft, [string]$fit) {
  Get-Process llama-server -ErrorAction SilentlyContinue | Stop-Process -Force
  Start-Sleep -Seconds 5
  $a = @('-m',$model,'-dev','ROCm0','-ngl','999','-fa','on','--load-mode','none',
    '-ctk','f16','-ctv','f16','-c',"$ctx",'-b',"$bub",'-ub',"$bub",
    '--parallel','1','--host','127.0.0.1','--port',"$Port",'--no-webui','--seed','1234')
  if ($draft) { $a += @('-md',$head,'--spec-type','draft-mtp','--spec-draft-n-max','2','--spec-draft-p-min','0.0','--n-gpu-layers-draft','999') }
  if ($fit -eq 'on') { $a += @('-fit','on') } else { $a += @('-fit','off') }
  $serr = Join-Path $res "b1a-$tag.err"; $sout = Join-Path $res "b1a-$tag.out"
  Remove-Item $serr,$sout -ErrorAction SilentlyContinue
  $p = Start-Process -FilePath $bin -ArgumentList $a -PassThru -RedirectStandardOutput $sout -RedirectStandardError $serr -NoNewWindow
  $ok=$false; $t0=Get-Date
  while (((Get-Date)-$t0).TotalSeconds -lt 360) {
    if ($p.HasExited) { break }
    try { if ((Invoke-WebRequest "http://127.0.0.1:$Port/health" -TimeoutSec 5 -UseBasicParsing).StatusCode -eq 200) { $ok=$true; break } } catch { Start-Sleep -Seconds 4 }
  }
  $exit = if ($p.HasExited) { $p.ExitCode } else { $null }
  $txt=''; foreach ($f in @($serr,$sout)) { if (Test-Path $f) { $txt += (Get-Content $f -Raw -ErrorAction SilentlyContinue) } }
  $fatal = (($txt -split "`n") | Where-Object { $_ -match 'invalid vector subscript|error loading model|failed to load|requires ctx_other|abort|Assertion|GGML_ASSERT|failed to measure' } | Select-Object -First 3)
  Write-Output ("[$tag] ctx=$ctx ub=$bub draft=$draft fit=$fit -> ready=$ok exit=$exit")
  foreach ($l in $fatal) { Write-Output ("      | " + $l.Trim()) }
  Start-Sleep -Seconds 2
  Get-Process llama-server -ErrorAction SilentlyContinue | Stop-Process -Force
  Start-Sleep -Seconds 3
  return [pscustomobject]@{ tag=$tag; ctx=$ctx; ub=$bub; draft=$draft; fit=$fit; ready=$ok; exit=$exit; fatal=($fatal -join ' | ') }
}

$rows = @()
# Bug A boundary: ub 2048 control vs ub 8192 at a large ctx, draft attached
$rows += Try-One 'a-ctx49152-ub2048-draft' 49152 2048 $true  'off'
$rows += Try-One 'a-ctx49152-ub8192-draft' 49152 8192 $true  'off'
# Bug A isolation: same ub 8192, no draft
$rows += Try-One 'a-ctx49152-ub8192-nodraft' 49152 8192 $false 'off'
# B1-fit: fit on, draft attached -> the ctx_other probe failure
$rows += Try-One 'fit-ctx32768-ub2048-draft' 32768 2048 $true 'on'
$rows | ConvertTo-Json -Depth 4 | Set-Content (Join-Path $res 'b1-bugA-repro.json')
Write-Output 'done'
