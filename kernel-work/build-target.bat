@echo off
REM incremental-build.ps1 helper: configure env and build only a named target.
REM usage: build-target.bat <target> [jobs]
setlocal
set SDK=C:\AI\sdk\therock1151
set SRC=C:\AI\build\strix-llama-win
set VC=C:\Program Files (x86)\Microsoft Visual Studio\2022\BuildTools\VC\Auxiliary\Build\vcvars64.bat
call "%VC%" >nul 2>&1
set "ROCM_PATH=%SDK%"
set "HIP_PATH=%SDK%"
set "HIP_DEVICE_LIB_PATH=%SDK%\lib\llvm\amdgcn\bitcode"
set "PATH=%SDK%\bin;%SDK%\lib\llvm\bin;%PATH%"
cd /d "%SRC%"
if "%~1"=="" (
  cmake --build build-therock -j 20
) else (
  cmake --build build-therock --target %1 -j %2
)
exit /b %errorlevel%
