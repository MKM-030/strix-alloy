# build-bwtest.ps1 — compile and run the HIP bandwidth microbenchmark with the TheRock SDK.
$ErrorActionPreference = 'Continue'
$sdk  = 'C:\AI\sdk\therock1151'
$src  = 'C:\Projects\REV-N-ornith-eval-20260911\kernel-work\bwtest.hip'
$out  = 'C:\Projects\REV-N-ornith-eval-20260911\kernel-work\bwtest.exe'
$log  = 'C:\Projects\REV-N-ornith-eval-20260911\kernel-work\results\bwtest.txt'

$vc = 'C:\Program Files (x86)\Microsoft Visual Studio\2022\BuildTools\VC\Auxiliary\Build\vcvars64.bat'

"==== bwtest $(Get-Date -Format o) ====" | Out-File $log -Encoding utf8
$cmds = @"
call "$vc"
set "ROCM_PATH=$sdk"
set "HIP_PATH=$sdk"
set "HIP_DEVICE_LIB_PATH=$sdk\lib\llvm\amdgcn\bitcode"
set "PATH=$sdk\bin;$sdk\lib\llvm\bin;%PATH%"
"$sdk\lib\llvm\bin\clang++.exe" -x hip --offload-arch=gfx1151 -O3 -o "$out" "$src" --rocm-path="$sdk" --rocm-device-lib-path="$sdk\lib\llvm\amdgcn\bitcode"
if errorlevel 1 ( echo COMPILE_FAILED & exit /b 1 )
echo COMPILED_OK
"$out" 4
"@
$bat = Join-Path $env:TEMP 'buildbwtest.bat'
Set-Content -Path $bat -Value $cmds -Encoding ascii
& cmd /c $bat 2>&1 | Tee-Object -FilePath $log -Append
"exit=$LASTEXITCODE" | Out-File $log -Append -Encoding utf8
