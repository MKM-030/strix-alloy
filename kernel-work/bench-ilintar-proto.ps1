# bench-ilintar-proto.ps1 — reproduce ilintar's exact measurement protocol with llama-bench.
# Their published number is pp16384 = 1204.31 t/s via `llama-bench -p 16384`. This runs the same
# protocol on our build so the comparison is apples-to-apples (no server/HTTP in the path).
param(
  [string]$Tag = "ilbench",
  [int]$Port = 0
)
$ErrorActionPreference = 'Continue'
$bin  = 'C:\AI\build\strix-llama-win\build-therock\bin\llama-bench.exe'
$sdk  = 'C:\AI\sdk\therock1151'
$root = 'C:\Projects\REV-N-ornith-eval-20260911\kernel-work'
$res  = Join-Path $root 'results'
$model = 'C:\AI\models\qwen38-flash\projfix\Qwen3.8-Flash-Next-IQ4_NL-PROJFIX-00001-of-00009.gguf'
$blog = Join-Path $res "$Tag.log"

Get-Process llama-server,llama-bench -ErrorAction SilentlyContinue | Stop-Process -Force
Start-Sleep -Seconds 3
$env:PATH = "$sdk\bin;$sdk\lib\llvm\bin;$env:PATH"
$env:ROCM_PATH = $sdk; $env:HIP_PATH = $sdk
$env:HIP_DEVICE_LIB_PATH = "$sdk\lib\llvm\amdgcn\bitcode"
$env:GGML_HIP_ENABLE_UNIFIED_MEMORY = '1'
$env:HSA_OVERRIDE_GFX_VERSION = '11.5.1'

# ilintar's protocol: pp16384, tg128, f16 KV, ub 16384, 3 reps
$a = @('-m',$model,'-dev','ROCm0','-ngl','99','-fa','1','-ctk','f16','-ctv','f16',
       '-b','16384','-ub','16384','-p','16384','-n','128','-r','3')

"==== $Tag (llama-bench, ilintar protocol) $(Get-Date -Format o) ====" | Out-File $blog -Append -Encoding utf8
"argv: $($a -join ' ')" | Out-File $blog -Append -Encoding utf8
$t0 = Get-Date
& $bin @a 2>&1 | Tee-Object -FilePath $blog -Append
"elapsed $([int]((Get-Date)-$t0).TotalSeconds)s exit=$LASTEXITCODE" | Out-File $blog -Append -Encoding utf8
Get-Process llama-bench -ErrorAction SilentlyContinue | Stop-Process -Force
