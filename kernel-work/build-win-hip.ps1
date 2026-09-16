# build-win-hip.ps1 — full native Windows HIP build of pwilkin strix-halo @ d67d5883 + prefetch stub.
param(
  [string]$Src = 'C:\AI\build\strix-llama-win',
  [int]$Jobs = 16
)
$ErrorActionPreference = 'Continue'
$rocm   = 'C:\Program Files\AMD\ROCm\7.2'
$build  = "$Src\build-win"
$vcvars = 'C:\Program Files (x86)\Microsoft Visual Studio\2022\BuildTools\VC\Auxiliary\Build\vcvars64.bat'
$log    = 'C:\Projects\REV-N-ornith-eval-20260911\kernel-work\results\win-build.log'

function Log($m) { $m | Tee-Object -FilePath $log -Append }

Log "===== native Windows HIP build $(Get-Date -Format o) ====="

# 1. stage source from the WSL checkout (it is already at win-native = d67d5883 + stub)
if (-not (Test-Path $Src)) {
  Log "copying source from WSL..."
  $dst = $Src
  New-Item -ItemType Directory -Force -Path $dst | Out-Null
  # robocopy from the WSL UNC share, excluding build dirs and .git
  $wslsrc = '\\wsl.localhost\Ubuntu-24.04\home\revn\strix-llama'
  robocopy $wslsrc $dst /E /XD build-hip .git build-win /NFL /NDL /NJH /NJS /MT:16 | Out-Null
  Log "robocopy exit=$LASTEXITCODE"
} else { Log "source already staged at $Src" }

# 2. verify the stub is present in the staged source
$lrh = Join-Path $Src 'src\llama-lazy-reader.h'
$stub = Select-String -Path $lrh -Pattern 'void prefetch\(const int32_t \*, int64_t\) const \{\}' -Quiet
Log "prefetch stub present: $stub"

# 3. configure + build in one cmd session with vcvars active
$cmds = @"
call "$vcvars"
set "ROCM_PATH=$rocm"
set "HIP_PATH=$rocm"
set "HIP_DEVICE_LIB_PATH=$rocm\amdgcn\bitcode"
set "PATH=$rocm\bin;$rocm\lib\llvm\bin;%PATH%"
cd /d "$Src"
cmake -S . -B build-win -G Ninja ^
  -DCMAKE_BUILD_TYPE=Release ^
  -DGGML_HIP=ON -DGGML_HIP_RCCL=OFF ^
  -DGPU_TARGETS=gfx1151 -DAMDGPU_TARGETS=gfx1151 ^
  -DGGML_HIP_GRAPHS=ON -DGGML_NATIVE=ON ^
  -DLLAMA_CURL=OFF -DLLAMA_BUILD_TESTS=OFF -DLLAMA_BUILD_EXAMPLES=OFF ^
  -DCMAKE_C_COMPILER="$rocm\bin\clang.exe" ^
  -DCMAKE_CXX_COMPILER="$rocm\bin\clang++.exe" ^
  -DCMAKE_HIP_COMPILER="$rocm\bin\clang++.exe" ^
  -DCMAKE_HIP_FLAGS="--rocm-path=$rocm --rocm-device-lib-path=$rocm\amdgcn\bitcode" ^
  -DCMAKE_PREFIX_PATH="$rocm"
if errorlevel 1 exit /b 1
cmake --build build-win --target llama-server llama-bench llama-cli -j $Jobs
exit /b %errorlevel%
"@
$bat = Join-Path $env:TEMP 'buildwin.bat'
Set-Content -Path $bat -Value $cmds -Encoding ascii
Log "running build (this takes a while)..."
& cmd /c $bat 2>&1 | Tee-Object -FilePath $log -Append
Log "build exit=$LASTEXITCODE"
$exe = "$build\bin\llama-server.exe"
Log "llama-server.exe exists: $(Test-Path $exe)"
