# build-win-hidden-dump.ps1 — add the hidden-dump tool to the native Windows TheRock build.
# Syncs only the new tool + tools/CMakeLists.txt, reconfigures, and builds just that target.
param([int]$Jobs = 12, [string]$Src = 'C:\AI\build\strix-llama-win')
$ErrorActionPreference = 'Continue'
$sdk  = 'C:\AI\sdk\therock1151'
$vc   = 'C:\Program Files (x86)\Microsoft Visual Studio\2022\BuildTools\VC\Auxiliary\Build\vcvars64.bat'
$log  = 'C:\Projects\REV-N-ornith-eval-20260911\kernel-work\results\hd-build.log'
function Log($m) { $m | Tee-Object -FilePath $log -Append }

Log "==== hidden-dump Windows build $(Get-Date -Format o) ===="
$wsl = '\\wsl.localhost\Ubuntu-24.04\home\revn\strix-llama'
New-Item -ItemType Directory -Force -Path (Join-Path $Src 'tools\hidden-dump') | Out-Null
Copy-Item (Join-Path $wsl 'tools\hidden-dump\hidden-dump.cpp') (Join-Path $Src 'tools\hidden-dump\hidden-dump.cpp') -Force
Copy-Item (Join-Path $wsl 'tools\hidden-dump\CMakeLists.txt') (Join-Path $Src 'tools\hidden-dump\CMakeLists.txt') -Force
Copy-Item (Join-Path $wsl 'tools\CMakeLists.txt') (Join-Path $Src 'tools\CMakeLists.txt') -Force
Log ("tool present: " + (Test-Path (Join-Path $Src 'tools\hidden-dump\hidden-dump.cpp')))
Log ("registered: " + (Select-String -Path (Join-Path $Src 'tools\CMakeLists.txt') -Pattern 'hidden-dump' -Quiet))

$cmds = @"
call "$vc"
set "ROCM_PATH=$sdk"
set "HIP_PATH=$sdk"
set "HIP_DEVICE_LIB_PATH=$sdk\lib\llvm\amdgcn\bitcode"
set "PATH=$sdk\bin;$sdk\lib\llvm\bin;%PATH%"
cd /d "$Src"
cmake -S . -B build-therock -G Ninja -DCMAKE_BUILD_TYPE=Release -DGGML_HIP=ON -DGGML_HIP_RCCL=OFF -DGPU_TARGETS=gfx1151 -DAMDGPU_TARGETS=gfx1151 -DGGML_HIP_GRAPHS=ON -DGGML_NATIVE=ON -DLLAMA_CURL=OFF -DLLAMA_BUILD_TESTS=OFF -DLLAMA_BUILD_EXAMPLES=OFF -DCMAKE_C_COMPILER="$sdk\lib\llvm\bin\clang.exe" -DCMAKE_CXX_COMPILER="$sdk\lib\llvm\bin\clang++.exe" -DCMAKE_HIP_COMPILER="$sdk\lib\llvm\bin\clang++.exe" -DCMAKE_HIP_FLAGS="--rocm-path=$sdk --rocm-device-lib-path=$sdk\lib\llvm\amdgcn\bitcode" -DCMAKE_PREFIX_PATH="$sdk"
if errorlevel 1 exit /b 1
cmake --build build-therock --target llama-hidden-dump -j $Jobs
exit /b %errorlevel%
"@
$bat = Join-Path $env:TEMP 'buildhd.bat'
Set-Content -Path $bat -Value $cmds -Encoding ascii
& cmd /c $bat 2>&1 | Tee-Object -FilePath $log -Append
Log ("build exit=" + $LASTEXITCODE)
Log ("exe: " + (Test-Path "$Src\build-therock\bin\llama-hidden-dump.exe"))
