<#
.SYNOPSIS
Build only the separate read-only ADLX system-power probe using the installed pinned SDK.
.DESCRIPTION
Does not run the probe, download anything, install packages, or change hardware/system settings.
The original GPU probe and its build directory remain untouched.
#>
[CmdletBinding()]
param()
$ErrorActionPreference = 'Stop'
$powerRepoRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '../..'))
$powerSdkRoot = Join-Path $powerRepoRoot 'artifacts/halogen-adlx/build/sdk/ADLX-d9f04a9bba022d6cf6333f005dd540b4ad19fb63'
$powerArchive = Join-Path $powerRepoRoot 'artifacts/halogen-adlx/build/adlx-v1.5.zip'
$powerSource = Join-Path $PSScriptRoot 'halogen_adlx_power_probe.cpp'
$powerOriginal = Join-Path $PSScriptRoot 'halogen_adlx_probe.cpp'
$powerHelper = Join-Path $powerSdkRoot 'SDK/ADLXHelper/Windows/Cpp/ADLXHelper.cpp'
$powerApis = Join-Path $powerSdkRoot 'SDK/Platform/Windows/WinAPIs.cpp'
$powerPins = @{
    $powerArchive = '2E0B3527C432B3F4A4EE7EA3974B266BAE208282684A451BCD347684BEC94312'
    $powerSource = 'FEA6F82F55A6DC544239EDFC899B2BC3C6EA2926A6F07BE9FE0C34BC68009EFA'
    $powerOriginal = '223920311CFFAAAAF2E23680A5209E80E195DF6B555793B6CBAE0997BDEB2801'
    $powerHelper = 'BFC9F5FBB0C560A6760D47F21BEE943A75C0B3303BA94475AD9E2587C66645C6'
    $powerApis = 'F6634E26499DEEA122A567A2972E80B49E02E3E11D7EAB9EB2BB6DFD77C3B04A'
    (Join-Path $powerSdkRoot 'SDK/Include/IPerformanceMonitoring1.h') = '981BBD7F7507E5A015D0F547EF2E2E53C50A3177FDF9A84130148ED6ECFE2E1F'
    (Join-Path $powerSdkRoot 'SDK/Include/IPowerTuning.h') = '614CFD7E4EB76755436135FF4AFDCA134DCE3986C600253F895FAC07D582EC46'
    (Join-Path $powerSdkRoot 'SDK/Include/ISystem1.h') = '1F8E73C2EC21DC9D66DBD0FCC5AD31AB2B6C5E4212E66E6A67B175C62EBAE880'
}
foreach ($powerPin in $powerPins.GetEnumerator()) {
    if ((Get-FileHash -LiteralPath $powerPin.Key -Algorithm SHA256).Hash -ne $powerPin.Value) {
        throw "Reviewed ADLX power-probe input changed: $($powerPin.Key)"
    }
}
$powerBuild = Join-Path $powerRepoRoot 'artifacts/halogen-adlx-power/build'
$powerProject = Join-Path $powerBuild 'project'
$powerOut = Join-Path $powerBuild 'out'
New-Item -ItemType Directory -Path $powerProject -Force | Out-Null
$powerCmakeSource = $powerSource.Replace('\', '/')
$powerCmakeSdk = $powerSdkRoot.Replace('\', '/')
$powerCmake = @"
cmake_minimum_required(VERSION 3.15)
project(halogen_adlx_power_probe LANGUAGES CXX)
add_executable(halogen_adlx_power_probe
  "$powerCmakeSource"
  "$powerCmakeSdk/SDK/ADLXHelper/Windows/Cpp/ADLXHelper.cpp"
  "$powerCmakeSdk/SDK/Platform/Windows/WinAPIs.cpp")
target_include_directories(halogen_adlx_power_probe PRIVATE "$powerCmakeSdk")
target_compile_features(halogen_adlx_power_probe PRIVATE cxx_std_17)
target_compile_options(halogen_adlx_power_probe PRIVATE /W4 /EHsc)
set_property(TARGET halogen_adlx_power_probe PROPERTY MSVC_RUNTIME_LIBRARY "MultiThreaded")
"@
Set-Content -LiteralPath (Join-Path $powerProject 'CMakeLists.txt') -Value $powerCmake -Encoding utf8
& cmake -S $powerProject -B $powerOut -G 'Visual Studio 17 2022' -A x64 | Out-Host
if ($LASTEXITCODE -ne 0) { throw 'ADLX power-probe configure failed' }
& cmake --build $powerOut --config Release | Out-Host
if ($LASTEXITCODE -ne 0) { throw 'ADLX power-probe build failed' }
$powerExecutable = Join-Path $powerOut 'Release/halogen_adlx_power_probe.exe'
[ordered]@{build_only=$true; executable=$powerExecutable;
    executable_sha256=(Get-FileHash -LiteralPath $powerExecutable -Algorithm SHA256).Hash;
    source_sha256=$powerPins[$powerSource]; sdk_commit='d9f04a9bba022d6cf6333f005dd540b4ad19fb63'} | ConvertTo-Json -Compress
