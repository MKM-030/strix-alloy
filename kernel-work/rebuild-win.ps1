# rebuild-win.ps1 — sync the two patched sources from WSL into the staged Windows tree and rebuild.
param([int]$Jobs = 16)
$ErrorActionPreference = 'Continue'
$rocm = 'C:\Program Files\AMD\ROCm\7.2'
$src  = 'C:\AI\build\strix-llama-win'
$vc   = 'C:\Program Files (x86)\Microsoft Visual Studio\2022\BuildTools\VC\Auxiliary\Build\vcvars64.bat'
$log  = 'C:\Projects\REV-N-ornith-eval-20260911\kernel-work\results\win-rebuild.log'
function Log($m) { $m | Tee-Object -FilePath $log -Append }

Log "==== rebuild $(Get-Date -Format o) ===="
$wsl = '\\wsl.localhost\Ubuntu-24.04\home\revn\strix-llama'
Copy-Item (Join-Path $wsl 'src\models\qwen4exp.cpp') (Join-Path $src 'src\models\qwen4exp.cpp') -Force
Copy-Item (Join-Path $wsl 'src\llama-lazy-reader.h')  (Join-Path $src 'src\llama-lazy-reader.h')  -Force
Log ("staged fix present: " + (Select-String -Path (Join-Path $src 'src\models\qwen4exp.cpp') -Pattern 'DRAFT_DENSE_ATTN' -Quiet))

$cmds = @"
call "$vc"
set "ROCM_PATH=$rocm"
set "HIP_PATH=$rocm"
set "HIP_DEVICE_LIB_PATH=$rocm\amdgcn\bitcode"
set "PATH=$rocm\bin;$rocm\lib\llvm\bin;%PATH%"
cd /d "$src"
cmake --build build-win --target llama-server -j $Jobs
exit /b %errorlevel%
"@
$bat = Join-Path $env:TEMP 'rebuildwin.bat'
Set-Content -Path $bat -Value $cmds -Encoding ascii
& cmd /c $bat 2>&1 | Tee-Object -FilePath $log -Append
Log ("build exit=" + $LASTEXITCODE)
Log ("exe: " + (Test-Path (Join-Path $src 'build-win\bin\llama-server.exe')))
