#requires -Version 5.1
# build-windows.ps1 — native Windows HIP build of the Strix Halo fork (gfx1151) with clang 24.
#
# Requires: TheRock Windows HIP SDK for gfx1151, MSVC BuildTools (for the Windows SDK / vcvars), Ninja.
# Adjust -Src / -Sdk / -Vc to your machine.
param(
    [string]$Src = 'C:\AI\build\strix-llama-win',                  # the llama.cpp fork checkout
    [string]$Sdk = 'C:\AI\sdk\therock1151',                        # TheRock gfx1151 SDK
    [string]$Vc  = 'C:\Program Files (x86)\Microsoft Visual Studio\2022\BuildTools\VC\Auxiliary\Build\vcvars64.bat',
    [int]$Jobs = 20,
    [switch]$SkipPin
)
$ErrorActionPreference = 'Stop'
$build = Join-Path $Src 'build-therock'

if (-not (Test-Path $Sdk)) { throw "SDK not found: $Sdk" }
if (-not (Test-Path $Vc))  { throw "vcvars64.bat not found: $Vc" }

Write-Output "SDK clang : $(& (Join-Path $Sdk 'lib\llvm\bin\clang.exe') --version 2>&1 | Select-Object -First 1)"
Write-Output "hipcc     : $(Test-Path (Join-Path $Sdk 'bin\hipcc.exe'))"
Write-Output "device libs: $(Test-Path (Join-Path $Sdk 'lib\llvm\amdgcn\bitcode'))"

$cmds = @"
call "$Vc"
set "ROCM_PATH=$Sdk"
set "HIP_PATH=$Sdk"
set "HIP_DEVICE_LIB_PATH=$Sdk\lib\llvm\amdgcn\bitcode"
set "PATH=$Sdk\bin;$Sdk\lib\llvm\bin;%PATH%"
cd /d "$Src"
cmake -S . -B build-therock -G Ninja ^
  -DCMAKE_BUILD_TYPE=Release ^
  -DGGML_HIP=ON -DGGML_HIP_RCCL=OFF ^
  -DGPU_TARGETS=gfx1151 -DAMDGPU_TARGETS=gfx1151 ^
  -DGGML_HIP_GRAPHS=ON -DGGML_NATIVE=ON ^
  -DLLAMA_CURL=OFF -DLLAMA_BUILD_TESTS=OFF -DLLAMA_BUILD_EXAMPLES=OFF ^
  -DCMAKE_C_COMPILER="$Sdk\lib\llvm\bin\clang.exe" ^
  -DCMAKE_CXX_COMPILER="$Sdk\lib\llvm\bin\clang++.exe" ^
  -DCMAKE_HIP_COMPILER="$Sdk\lib\llvm\bin\clang++.exe" ^
  -DCMAKE_HIP_FLAGS="--rocm-path=$Sdk --rocm-device-lib-path=$Sdk\lib\llvm\amdgcn\bitcode" ^
  -DCMAKE_PREFIX_PATH="$Sdk"
if errorlevel 1 exit /b 1
cmake --build build-therock --target llama-server llama-bench -j $Jobs
exit /b %errorlevel%
"@

$bat = Join-Path $env:TEMP 'strix-alloy-build.bat'
Set-Content -Path $bat -Value $cmds -Encoding ascii
Write-Output 'configuring + building...'
& cmd /c $bat
if ($LASTEXITCODE -ne 0) { throw "build failed with exit $LASTEXITCODE" }

$binDir = Join-Path $build 'bin'
Write-Output "exe present: $(Test-Path (Join-Path $binDir 'llama-server.exe'))"

if (-not $SkipPin) {
    Write-Output ''
    Write-Output 'pinning HIP runtime DLLs beside the exe (see setup/README.md for why this matters)...'
    & (Join-Path $PSScriptRoot 'pin-hip-dlls.ps1') -Sdk $Sdk -BinDir $binDir
}
