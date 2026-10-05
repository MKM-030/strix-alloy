# SPDX-License-Identifier: Apache-2.0 WITH LLVM-exception
# Build only. Run from the existing x64 MSVC Native Tools environment.
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$OutDir,
    [ValidateSet('control', 'gemv-vector', 'gemv-scalar')]
    [string[]]$Modes = @('control', 'gemv-vector'),
    [string]$Python = 'C:\AI\runtimes\ironenv\Scripts\python.exe',
    [string]$MlirRoot = 'C:\AI\runtimes\ironenv\Lib\site-packages\mlir_aie',
    [string]$PeanoRoot = 'C:\AI\runtimes\ironenv\Lib\site-packages\llvm-aie',
    [string]$XrtRoot = 'C:\Xilinx\XRT'
)

$ErrorActionPreference = 'Stop'
$taskSource = [System.IO.Path]::GetFullPath($PSScriptRoot)
$taskOutput = [System.IO.Path]::GetFullPath($OutDir)
if (Test-Path -LiteralPath $taskOutput) {
    throw "OutDir must be a fresh directory: $taskOutput"
}
if ($Modes.Count -eq 0 -or ($Modes | Select-Object -Unique).Count -ne $Modes.Count) {
    throw 'Modes must be a nonempty list without duplicates.'
}
$taskAiecc = Join-Path $MlirRoot 'bin\aiecc.exe'
$taskPeano = Join-Path $PeanoRoot 'bin\clang++.exe'
$taskRequired = @(
    $Python, $taskAiecc, $taskPeano,
    (Join-Path $MlirRoot 'include\aie_api\aie.hpp'),
    (Join-Path $XrtRoot 'include\xrt\experimental\xrt_xclbin.h'),
    (Join-Path $XrtRoot 'lib\xrt_coreutil.lib'),
    (Join-Path $XrtRoot 'xclbinutil.exe')
)
foreach ($taskPath in $taskRequired) {
    if (-not (Test-Path -LiteralPath $taskPath -PathType Leaf)) {
        throw "Required installed tool/header/library is missing: $taskPath"
    }
}
$taskCl = Get-Command 'cl.exe' -CommandType Application -ErrorAction Stop
$taskOldPath = $env:PATH
$taskOldPythonPath = $env:PYTHONPATH
$taskOldBytecode = $env:PYTHONDONTWRITEBYTECODE
$taskStarted = [DateTime]::UtcNow
$taskReceipt = [ordered]@{
    format = 'halogen-native-dispatch-build-v1'
    started_utc = $taskStarted.ToString('o')
    source_dir = $taskSource
    output_dir = $taskOutput
    modes = @($Modes)
    python = $Python
    aiecc = $taskAiecc
    peano = $taskPeano
    xrt_sdk = $XrtRoot
    msvc = $taskCl.Source
    runtime_executed = $false
    build_succeeded = $false
    source_hashes = @()
    artifact_hashes = @()
}
New-Item -ItemType Directory -Path $taskOutput | Out-Null
try {
    # Process-local environment only; restored even when a compiler fails.
    $env:PATH = "$MlirRoot\bin;$PeanoRoot\bin;$XrtRoot;$taskOldPath"
    $env:PYTHONPATH = "$MlirRoot\python" + $(if ($taskOldPythonPath) { ";$taskOldPythonPath" } else { '' })
    $env:PYTHONDONTWRITEBYTECODE = '1'
    foreach ($taskName in @('generate.py', 'contract.h', 'kernels.cc', 'host.cpp', 'build.ps1', 'README.md', 'LICENSE.txt')) {
        $taskHash = Get-FileHash -LiteralPath (Join-Path $taskSource $taskName) -Algorithm SHA256
        $taskReceipt.source_hashes += [ordered]@{ name = $taskName; sha256 = $taskHash.Hash.ToLowerInvariant() }
    }

    Push-Location -LiteralPath $taskOutput
    try {
        & $taskCl.Source '/nologo' '/std:c++17' '/Zc:__cplusplus' '/EHsc' '/O2' "/I$XrtRoot\include" `
            (Join-Path $taskSource 'host.cpp') "/Fe:$(Join-Path $taskOutput 'host.exe')" `
            '/link' "/LIBPATH:$XrtRoot\lib" 'xrt_coreutil.lib'
        if ($LASTEXITCODE -ne 0) { throw "MSVC host compile failed with exit $LASTEXITCODE" }
    }
    finally { Pop-Location }

    foreach ($taskMode in $Modes) {
        $taskModeDir = Join-Path $taskOutput $taskMode
        New-Item -ItemType Directory -Path $taskModeDir | Out-Null
        Push-Location -LiteralPath $taskModeDir
        try {
            & $Python (Join-Path $taskSource 'generate.py') '--mode' $taskMode `
                '--mlir' 'design.mlir' '--abi' 'design.abi'
            if ($LASTEXITCODE -ne 0) { throw "Generator failed for $taskMode with exit $LASTEXITCODE" }
            $taskFlags = @('--target=aie2p-none-unknown-elf', '-O2', '-std=c++20',
                '-D__AIE_API_AIE_ADF_HPP__', "-I$MlirRoot\include", "-I$taskSource",
                '-ffunction-sections', '-fdata-sections', '-fstack-size-section')
            if ($taskMode -eq 'gemv-vector') { $taskFlags += '-DDISPATCH_ENABLE_VECTOR=1' }
            & $taskPeano @taskFlags '-c' (Join-Path $taskSource 'kernels.cc') '-o' 'kernels.o'
            if ($LASTEXITCODE -ne 0) { throw "Peano kernel compile failed for $taskMode with exit $LASTEXITCODE" }
            & $taskAiecc '--aie-generate-xclbin' '--xclbin-name=design.xclbin' `
                '--aie-generate-npu-insts' '--npu-insts-name=insts.bin' '--xclbin-kernel-name=MLIR_AIE' `
                '--no-xchesscc' '--no-xbridge' '--no-compile-host' `
                "--peano=$PeanoRoot" "--tmpdir=$(Join-Path $taskModeDir 'intermediates')" `
                '--dump-intermediates' 'design.mlir'
            if ($LASTEXITCODE -ne 0) { throw "aiecc failed for $taskMode with exit $LASTEXITCODE" }
            foreach ($taskName in @('design.mlir', 'design.abi', 'kernels.o', 'design.xclbin', 'insts.bin')) {
                $taskArtifact = Join-Path $taskModeDir $taskName
                $taskHash = Get-FileHash -LiteralPath $taskArtifact -Algorithm SHA256
                $taskReceipt.artifact_hashes += [ordered]@{
                    mode = $taskMode; name = $taskName
                    bytes = (Get-Item -LiteralPath $taskArtifact).Length
                    sha256 = $taskHash.Hash.ToLowerInvariant()
                }
            }
        }
        finally { Pop-Location }
    }
    $taskHash = Get-FileHash -LiteralPath (Join-Path $taskOutput 'host.exe') -Algorithm SHA256
    $taskReceipt.artifact_hashes += [ordered]@{ name = 'host.exe'; sha256 = $taskHash.Hash.ToLowerInvariant() }
    $taskReceipt.build_succeeded = $true
}
catch {
    $taskReceipt.error = $_.Exception.Message
    throw
}
finally {
    $env:PATH = $taskOldPath
    $env:PYTHONPATH = $taskOldPythonPath
    $env:PYTHONDONTWRITEBYTECODE = $taskOldBytecode
    $taskReceipt.finished_utc = [DateTime]::UtcNow.ToString('o')
    $taskReceipt | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath (Join-Path $taskOutput 'build-receipt.json') -Encoding utf8
}
Write-Output "Build artifacts and receipt: $taskOutput"
Write-Output 'No host execution was performed.'
