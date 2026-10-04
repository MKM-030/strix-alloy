<#!
.SYNOPSIS
Build and run the app-local read-only ADLX GPU capability/telemetry probe.
.DESCRIPTION
Downloads AMD's official v1.5 SDK at a pinned commit, verifies its archive hash,
and builds with existing Visual Studio C++ Build Tools. No package installation,
hardware setting, metrics tracking, or global environment change is performed.
Build and SDK byproducts remain in the repository's ignored build directory.
#>
[CmdletBinding()]
param(
    [ValidateRange(1, 86400)][int]$Samples = 5,
    [ValidateRange(100, 60000)][int]$IntervalMs = 1000,
    [string]$BuildDirectory,
    [string]$OutputPath,
    [switch]$BuildOnly
)
$ErrorActionPreference = 'Stop'
$adlxRepoRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '../..'))
if (-not $BuildDirectory) { $BuildDirectory = Join-Path $adlxRepoRoot 'artifacts/halogen-adlx/build' }
$BuildDirectory = [IO.Path]::GetFullPath($BuildDirectory)
$adlxCommit = 'd9f04a9bba022d6cf6333f005dd540b4ad19fb63'
$adlxArchiveHash = '2E0B3527C432B3F4A4EE7EA3974B266BAE208282684A451BCD347684BEC94312'
$adlxSdkRoot = Join-Path $BuildDirectory "sdk/ADLX-$adlxCommit"
$adlxArchive = Join-Path $BuildDirectory 'adlx-v1.5.zip'
$adlxProject = Join-Path $BuildDirectory 'project'
$adlxBinaryBuild = Join-Path $BuildDirectory 'out'
$adlxExecutable = Join-Path $adlxBinaryBuild 'Release/halogen_adlx_probe.exe'
$adlxSource = Join-Path $PSScriptRoot 'halogen_adlx_probe.cpp'
New-Item -ItemType Directory -Path $BuildDirectory, $adlxProject -Force | Out-Null
if (-not (Test-Path -LiteralPath $adlxArchive)) {
    Invoke-WebRequest -Uri "https://codeload.github.com/GPUOpen-LibrariesAndSDKs/ADLX/zip/$adlxCommit" -OutFile $adlxArchive
}
if ((Get-FileHash -LiteralPath $adlxArchive -Algorithm SHA256).Hash -ne $adlxArchiveHash) {
    throw "Official ADLX archive checksum mismatch: $adlxArchive"
}
if (-not (Test-Path -LiteralPath (Join-Path $adlxSdkRoot 'SDK/Include/ADLX.h'))) {
    Expand-Archive -LiteralPath $adlxArchive -DestinationPath (Join-Path $BuildDirectory 'sdk')
}
$adlxCmakeSource = $adlxSource.Replace('\', '/')
$adlxCmakeSdk = $adlxSdkRoot.Replace('\', '/')
$adlxCmakeText = @"
cmake_minimum_required(VERSION 3.15)
project(halogen_adlx_probe LANGUAGES CXX)
add_executable(halogen_adlx_probe
  "$adlxCmakeSource"
  "$adlxCmakeSdk/SDK/ADLXHelper/Windows/Cpp/ADLXHelper.cpp"
  "$adlxCmakeSdk/SDK/Platform/Windows/WinAPIs.cpp")
target_include_directories(halogen_adlx_probe PRIVATE "$adlxCmakeSdk")
target_compile_features(halogen_adlx_probe PRIVATE cxx_std_17)
target_compile_options(halogen_adlx_probe PRIVATE /W4 /EHsc)
set_property(TARGET halogen_adlx_probe PROPERTY MSVC_RUNTIME_LIBRARY "MultiThreaded")
"@
Set-Content -LiteralPath (Join-Path $adlxProject 'CMakeLists.txt') -Value $adlxCmakeText -Encoding utf8
& cmake -S $adlxProject -B $adlxBinaryBuild -G 'Visual Studio 17 2022' -A x64 | Out-Host
if ($LASTEXITCODE -ne 0) { throw 'ADLX CMake configure failed' }
& cmake --build $adlxBinaryBuild --config Release | Out-Host
if ($LASTEXITCODE -ne 0) { throw 'ADLX probe build failed' }
if ($BuildOnly) { Write-Output $adlxExecutable; return }
if (-not $OutputPath) { $OutputPath = Join-Path $BuildDirectory ("results/adlx-{0}.ndjson" -f (Get-Date -Format 'yyyyMMdd-HHmmss-fff')) }
$OutputPath = [IO.Path]::GetFullPath($OutputPath)
New-Item -ItemType Directory -Path ([IO.Path]::GetDirectoryName($OutputPath)) -Force | Out-Null
$adlxDll = Join-Path $env:WINDIR 'System32/amdadlx64.dll'
$adlxMetadata = [ordered]@{
    record = 'run_context'; started_utc = [DateTime]::UtcNow.ToString('o'); read_only = $true
    sdk_commit = $adlxCommit; sdk_archive_sha256 = $adlxArchiveHash
    executable = $adlxExecutable; executable_sha256 = (Get-FileHash -LiteralPath $adlxExecutable -Algorithm SHA256).Hash
    source_sha256 = (Get-FileHash -LiteralPath $adlxSource -Algorithm SHA256).Hash
    system_adlx_dll = $adlxDll; system_adlx_dll_version = (Get-Item -LiteralPath $adlxDll).VersionInfo.FileVersion
    system_adlx_dll_sha256 = (Get-FileHash -LiteralPath $adlxDll -Algorithm SHA256).Hash
}
$adlxOutputStream = [IO.File]::Open($OutputPath, [IO.FileMode]::CreateNew,
    [IO.FileAccess]::Write, [IO.FileShare]::Read)
$adlxWriter = [IO.StreamWriter]::new($adlxOutputStream, [Text.UTF8Encoding]::new($false))
try {
    $adlxContextLine = $adlxMetadata | ConvertTo-Json -Compress
    $adlxWriter.WriteLine($adlxContextLine)
    Write-Output $adlxContextLine
    & $adlxExecutable --samples $Samples --interval-ms $IntervalMs | ForEach-Object {
        $adlxWriter.WriteLine($_)
        $adlxWriter.Flush()
        Write-Output $_
    }
    $adlxProbeExitCode = $LASTEXITCODE
} finally {
    $adlxWriter.Dispose()
}
Write-Host "ADLX NDJSON: $OutputPath"
Write-Host "SHA256: $((Get-FileHash -LiteralPath $OutputPath -Algorithm SHA256).Hash)"
if ($adlxProbeExitCode -ne 0) { throw "ADLX probe exited $adlxProbeExitCode; inspect $OutputPath" }
