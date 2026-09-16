# build-win-therock.ps1 — native Windows HIP build using the TheRock 10.2 gfx1151 SDK (clang 24).
param([int]$Jobs = 20, [string]$Src = 'C:\AI\build\strix-llama-win')
$ErrorActionPreference = 'Continue'
$sdk  = 'C:\AI\sdk\therock1151'
$build = "$Src\build-therock"
$vc   = 'C:\Program Files (x86)\Microsoft Visual Studio\2022\BuildTools\VC\Auxiliary\Build\vcvars64.bat'
$log  = 'C:\Projects\REV-N-ornith-eval-20260911\kernel-work\results\therock-build.log'
function Log($m) { $m | Tee-Object -FilePath $log -Append }

Log "==== TheRock clang 24 build $(Get-Date -Format o) ===="
Log ("sdk clang: " + (& "$sdk\lib\llvm\bin\clang.exe" --version 2>&1 | Select-Object -First 1))
Log ("hipcc: " + (Test-Path "$sdk\bin\hipcc.exe"))
Log ("device libs: " + (Test-Path "$sdk\lib\llvm\amdgcn\bitcode"))

# sync the patched sources from WSL
#
# This used to copy exactly three files (llama-lazy-reader.h, qwen4exp.cpp, server-context.cpp).
# That silently skipped ggml/src/ggml-cuda, so a HIP kernel change compiled from a stale tree and the
# "measured" result described a build that did not contain the patch. Sync the whole trees the fork
# actually modifies instead of a hand-kept list.
$wsl = '\\wsl.localhost\Ubuntu-24.04\home\revn\strix-llama'
$syncDirs = @('src', 'common', 'tools', 'ggml')
foreach ($d in $syncDirs) {
    $from = Join-Path $wsl $d
    $to   = Join-Path $Src $d
    if (-not (Test-Path $from)) { Log "  sync SKIP (absent): $d"; continue }
    # robocopy: /E all subdirs, /NFL /NDL quiet, /NJH /NJS no headers; exit codes 0-7 are success
    & robocopy $from $to /E /NFL /NDL /NJH /NJS /R:1 /W:1 /XD build build-* .git | Out-Null
    Log ("  synced $d (robocopy exit $LASTEXITCODE)")
}
Copy-Item (Join-Path $wsl 'src\llama-lazy-reader.h') (Join-Path $Src 'src\llama-lazy-reader.h') -Force
Copy-Item (Join-Path $wsl 'src\models\qwen4exp.cpp') (Join-Path $Src 'src\models\qwen4exp.cpp') -Force
Copy-Item (Join-Path $wsl 'tools\server\server-context.cpp') (Join-Path $Src 'tools\server\server-context.cpp') -Force
Log ("stub present: " + (Select-String -Path (Join-Path $Src 'src\llama-lazy-reader.h') -Pattern 'prefetch\(const int32_t \*, int64_t\) const \{\}' -Quiet))
Log ("ON_DEVICE ckpt sites: " + (Select-String -Path (Join-Path $Src 'tools\server\server-context.cpp') -Pattern 'ON_DEVICE' | Measure-Object).Count)
Log ("d2t refs in staged qwen4exp: " + (Select-String -Path (Join-Path $Src 'src\models\qwen4exp.cpp') -Pattern 'd2t' | Measure-Object).Count)
# prove the HIP patch actually landed in the build tree, not just in WSL
Log ("MMID_512 in staged mmid.cu: " + (Select-String -Path (Join-Path $Src 'ggml\src\ggml-cuda\mmid.cu') -Pattern 'mm_ids_helper_512_10' -Quiet))

$cmds = @"
call "$vc"
set "ROCM_PATH=$sdk"
set "HIP_PATH=$sdk"
set "HIP_DEVICE_LIB_PATH=$sdk\lib\llvm\amdgcn\bitcode"
set "PATH=$sdk\bin;$sdk\lib\llvm\bin;%PATH%"
cd /d "$Src"
cmake -S . -B build-therock -G Ninja ^
  -DCMAKE_BUILD_TYPE=Release ^
  -DGGML_HIP=ON -DGGML_HIP_RCCL=OFF ^
  -DGPU_TARGETS=gfx1151 -DAMDGPU_TARGETS=gfx1151 ^
  -DGGML_HIP_GRAPHS=ON -DGGML_NATIVE=ON ^
  -DLLAMA_CURL=OFF -DLLAMA_BUILD_TESTS=OFF -DLLAMA_BUILD_EXAMPLES=OFF ^
  -DCMAKE_C_COMPILER="$sdk\lib\llvm\bin\clang.exe" ^
  -DCMAKE_CXX_COMPILER="$sdk\lib\llvm\bin\clang++.exe" ^
  -DCMAKE_HIP_COMPILER="$sdk\lib\llvm\bin\clang++.exe" ^
  -DCMAKE_HIP_FLAGS="--rocm-path=$sdk --rocm-device-lib-path=$sdk\lib\llvm\amdgcn\bitcode" ^
  -DCMAKE_PREFIX_PATH="$sdk"
if errorlevel 1 exit /b 1
cmake --build build-therock --target llama-server llama-bench -j $Jobs
exit /b %errorlevel%
"@
$bat = Join-Path $env:TEMP 'buildtherock.bat'
Set-Content -Path $bat -Value $cmds -Encoding ascii
Log "configuring + building..."
& cmd /c $bat 2>&1 | Tee-Object -FilePath $log -Append
Log ("build exit=" + $LASTEXITCODE)
Log ("exe: " + (Test-Path "$build\bin\llama-server.exe"))

# ---- pin the HIP runtime beside the binaries -------------------------------------------------
# ggml-hip.dll imports "amdhip64_7.dll" by NAME. Windows searches the exe's own directory first,
# then System32, then PATH. With no local copy, the GPU driver's copy in C:\Windows\System32
# shadows the SDK's, and HIP fails at device init with:
#     cudaMemGetInfo failed (invalid argument), returning 0/0
# (Symptom is confusing: the SDK's own hipInfo.exe works, because it resolves its own directory.)
# Copying the SDK runtime beside the exe makes the correct pair win. Doing it here means a
# rebuild can never reintroduce the shadowing.
$sdkBin = "$sdk\bin"
foreach ($f in @('amdhip64_7.dll','amd_comgr.dll','amdocl64.dll')) {
    $src = Join-Path $sdkBin $f
    $dst = Join-Path "$build\bin" $f
    if (Test-Path $src) {
        if (Test-Path $dst) {
            $a = (Get-Item $src).Length; $b = (Get-Item $dst).Length
            if ($a -ne $b) { Copy-Item $src $dst -Force; Log "  pinned $f ($b -> $a bytes)" }
            else { Log "  $f already matches SDK" }
        } else {
            Copy-Item $src $dst -Force; Log "  pinned $f (new)"
        }
    } else { Log "  WARNING: SDK runtime missing: $src" }
}
