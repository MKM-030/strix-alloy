#requires -Version 7.0
[CmdletBinding()]
param(
 [Parameter(Mandatory)][string]$SourceDirectory,
 [Parameter(Mandatory)][string]$SdkDirectory,
 [Parameter(Mandatory)][string]$VcpkgDirectory,
 [ValidateRange(1,8)][int]$Jobs=2,
 [switch]$TestsOnly
)
$ErrorActionPreference='Stop'
$source=(Resolve-Path -LiteralPath $SourceDirectory).Path.Replace('\','/')
$sdk=(Resolve-Path -LiteralPath $SdkDirectory).Path.Replace('\','/')
$vp=(Resolve-Path -LiteralPath $VcpkgDirectory).Path.Replace('\','/')
& python (Join-Path $PSScriptRoot 'verify_toolchain.py') --sdk $sdk --source $source
if($LASTEXITCODE -ne 0){throw 'Unqualified GUFO toolchain/source; no build was configured'}
if(-not(Test-Path "$vp/installed/x64-windows/lib")){throw 'Install the pinned GUFO vcpkg dependencies first'}
$build="$source/build/gpu-test-100"
$active=Get-CimInstance Win32_Process | Where-Object { $_.ExecutablePath -and $_.ExecutablePath.Replace('\','/').StartsWith($build+'/',[StringComparison]::OrdinalIgnoreCase) }
if($active){throw 'A process is using this build; stop it before rebuilding or replacing DLLs'}
$vswhere=Join-Path ([Environment]::GetFolderPath('ProgramFilesX86')) 'Microsoft Visual Studio/Installer/vswhere.exe'
$vs=& $vswhere -latest -products * -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath
if(-not $vs){throw 'Visual Studio C++ Build Tools not found'}
$vcvars=Join-Path $vs 'VC/Auxiliary/Build/vcvars64.bat'
cmd /c "`"$vcvars`" >nul && set"|ForEach-Object {if($_ -match '^([^=]+)=(.*)$'){Set-Item "env:$($matches[1])" $matches[2]}}
$env:HIP_PATH=$sdk; $env:HIP_DEVICE_LIB_PATH="$sdk/lib/llvm/amdgcn/bitcode"
$env:PATH="$sdk/bin;$sdk/lib/llvm/bin;$env:PATH"
$ninja=(Get-Command ninja -ErrorAction Stop).Source.Replace('\','/')
cmake -S $source --preset gpu-test -B $build "-DCMAKE_MAKE_PROGRAM=$ninja" `
 "-DCMAKE_C_COMPILER=$sdk/lib/llvm/bin/clang.exe" "-DCMAKE_CXX_COMPILER=$sdk/lib/llvm/bin/clang++.exe" `
 "-DCMAKE_HIP_COMPILER=$sdk/lib/llvm/bin/clang++.exe" "-DCMAKE_TOOLCHAIN_FILE=$vp/scripts/buildsystems/vcpkg.cmake" `
 -DVCPKG_MANIFEST_MODE=OFF "-DVCPKG_INSTALLED_DIR=$vp/installed" -DVCPKG_TARGET_TRIPLET=x64-windows `
 "-DCMAKE_PREFIX_PATH=$sdk" -DCMAKE_LINKER_TYPE=LLD -DGUFO_VERSION=7e924c2d787a-therock100 `
 '-DCMAKE_HIP_FLAGS_RELWITHDEBINFO=-O2 -DNDEBUG -g0'
if($LASTEXITCODE -ne 0){throw 'CMake configuration failed'}
$targets=@('qwen38_flash_next_tests')
if(-not $TestsOnly){$targets+=@('gufo','qwen38_flash_next_gpu_probe')}
cmake --build $build --target @targets --parallel $Jobs
if($LASTEXITCODE -ne 0){throw 'GUFO build failed'}
# Application-local runtime: do not accidentally load the display driver's HIP DLL.
Get-ChildItem "$sdk/bin/*.dll"|Copy-Item -Destination $build -Force
Get-ChildItem "$vp/installed/x64-windows/bin/*.dll"|Copy-Item -Destination $build -Force
foreach($dir in @('hipblaslt','rocblas')){
 if(Test-Path "$sdk/bin/$dir"){Copy-Item "$sdk/bin/$dir" -Destination $build -Recurse -Force}
}
if($env:VCToolsRedistDir){
 Get-ChildItem "$env:VCToolsRedistDir/x64/Microsoft.VC*.CRT/*.dll"|Copy-Item -Destination $build -Force
 $omp=Get-ChildItem "$env:VCToolsRedistDir/debug_nonredist/x64/Microsoft.VC*.OpenMP.LLVM/libomp140.x86_64.dll" -ErrorAction SilentlyContinue
 if($omp){$omp|Copy-Item -Destination $build -Force}
}
Write-Output "Built $build. Run numerical qualification before any model load. This local dependency directory is not a redistributable package."
