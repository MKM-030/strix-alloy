# op-decode.ps1 — decode-DOMINATED per-op profile, target-only vs target+MTP.
# Long generation + small prompt so the cumulative op aggregates are dominated by decode evals.
param([int]$Prompt = 1024, [int]$Gen = 1024, [int]$Ctx = 4096, [int]$Port = 8285)
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
$env:LLAMA_OP_TIMING = '2'
$env:LLAMA_OP_TIMING_EVERY = '64'
$env:LLAMA_OP_TIMING_OPS = 'mul_mat,mul_mat_id,ssm,gated_delta,flash_attn,get_rows,top_k,moe,softmax,rope,norm,rms_norm,cont,add,silu,cpy,scale,concat,repeat,sub,log,unary,pad,permute,transpose,set_rows'

function RunArm([string]$tag, [bool]$useMtp) {
  Get-Process llama-server -ErrorAction SilentlyContinue | Stop-Process -Force
  Start-Sleep -Seconds 4
  $a = @('-m',$model,'-dev','ROCm0','-ngl','999','-fa','on','-fit','off','--load-mode','none',
    '-ctk','f16','-ctv','f16','-c',"$Ctx",'-b','2048','-ub','2048','--parallel','1',
    '--host','127.0.0.1','--port',"$Port",'--no-webui')
  if ($useMtp) { $a += @('-md',$head,'--spec-type','draft-mtp','--spec-draft-n-max','2') }
  $serr = Join-Path $res "opd-$tag.err"; $sout = Join-Path $res "opd-$tag.out"
  Remove-Item $serr,$sout -ErrorAction SilentlyContinue
  $p = Start-Process -FilePath $bin -ArgumentList $a -PassThru -RedirectStandardOutput $sout -RedirectStandardError $serr -NoNewWindow
  $ok=$false; $t0=Get-Date
  while (((Get-Date)-$t0).TotalSeconds -lt 900) {
    if ($p.HasExited) { Write-Output "[$tag] EXITED $($p.ExitCode)"; break }
    try { if ((Invoke-WebRequest "http://127.0.0.1:$Port/health" -TimeoutSec 5 -UseBasicParsing).StatusCode -eq 200) { $ok=$true; break } } catch { Start-Sleep -Seconds 5 }
  }
  if ($ok) {
    Write-Output "[$tag] READY $([int]((Get-Date)-$t0).TotalSeconds)s"
    # warm, then the long decode
    python "$root\fnbench.py" --port $Port --label "opd-$tag-warm" --sizes "$Prompt" --gen 64 --repeats 1 --out (Join-Path $res "opd-$tag-warm.json") 2>&1 | Out-Null
    python "$root\fnbench.py" --port $Port --label "opd-$tag" --sizes "$Prompt" --gen $Gen --repeats 1 --out (Join-Path $res "opd-$tag.json") 2>&1 |
      Select-String -Pattern 'n=|decode'
  }
  Start-Sleep -Seconds 2
  Get-Process llama-server -ErrorAction SilentlyContinue | Stop-Process -Force
  Start-Sleep -Seconds 3
}

RunArm 'nomtp' $false
RunArm 'mtp'   $true
Write-Output 'done'
