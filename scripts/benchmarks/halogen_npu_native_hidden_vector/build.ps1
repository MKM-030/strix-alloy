# SPDX-License-Identifier: Apache-2.0 WITH LLVM-exception
# Existing x64 Native Tools environment. Offline build only, never device launch.
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$OutDir,
    [string]$Python = 'C:\AI\runtimes\ironenv\Scripts\python.exe',
    [string]$MlirRoot = 'C:\AI\runtimes\ironenv\Lib\site-packages\mlir_aie',
    [string]$PeanoRoot = 'C:\AI\runtimes\ironenv\Lib\site-packages\llvm-aie',
    [string]$XrtRoot = 'C:\Xilinx\XRT'
)
$ErrorActionPreference = 'Stop'
$taskSource = [System.IO.Path]::GetFullPath($PSScriptRoot)
$taskOutput = [System.IO.Path]::GetFullPath($OutDir)
if (Test-Path -LiteralPath $taskOutput) { throw "OutDir must be fresh: $taskOutput" }
$taskCl = Get-Command 'cl.exe' -CommandType Application -ErrorAction Stop
$taskAiecc = Join-Path $MlirRoot 'bin\aiecc.exe'
$taskPeano = Join-Path $PeanoRoot 'bin\clang++.exe'
foreach ($taskPath in @($Python, $taskAiecc, $taskPeano,
    (Join-Path $MlirRoot 'include\aie_api\aie.hpp'),
    (Join-Path $XrtRoot 'include\xrt\experimental\xrt_xclbin.h'),
    (Join-Path $XrtRoot 'lib\xrt_coreutil.lib'),
    (Join-Path $taskSource '..\halogen_mtp_h_wire.h'))) {
    if (-not (Test-Path -LiteralPath $taskPath -PathType Leaf)) { throw "Missing installed dependency: $taskPath" }
}
$taskOldPath = $env:PATH
$taskOldPythonPath = $env:PYTHONPATH
$taskOldBytecode = $env:PYTHONDONTWRITEBYTECODE
$taskReceipt = [ordered]@{
    format = 'halogen-native-hidden-vector-build-v1'; started_utc = [DateTime]::UtcNow.ToString('o')
    source_dir = $taskSource; output_dir = $taskOutput; python = $Python
    aiecc = $taskAiecc; peano = $taskPeano; xrt_sdk = $XrtRoot; msvc = $taskCl.Source
    device_opened = $false; runtime_executed = $false; build_succeeded = $false
    source_hashes = @(); artifact_hashes = @()
}
New-Item -ItemType Directory -Path $taskOutput | Out-Null
try {
    $env:PATH = "$MlirRoot\bin;$PeanoRoot\bin;$XrtRoot;$taskOldPath"
    $env:PYTHONPATH = "$MlirRoot\python" + $(if ($taskOldPythonPath) { ";$taskOldPythonPath" } else { '' })
    $env:PYTHONDONTWRITEBYTECODE = '1'
    foreach ($taskName in @('generate.py','contract.h','bf16_round.h','kernels.cc','host.cpp','pack.py','numeric_reference.py',
        'test_pack.py','verify_emission.py','build.ps1','README.md','LICENSE.txt',
        'native_tcp_adapter.cpp','TCP_ADAPTER.md','..\halogen_mtp_h_wire.h')) {
        $taskHash = Get-FileHash -LiteralPath (Join-Path $taskSource $taskName) -Algorithm SHA256
        $taskReceipt.source_hashes += [ordered]@{ name = $taskName; sha256 = $taskHash.Hash.ToLowerInvariant() }
    }
    Push-Location -LiteralPath $taskOutput
    try {
        & $taskCl.Source '/nologo' '/std:c++17' '/Zc:__cplusplus' '/EHsc' '/O2' '/fp:strict' "/I$XrtRoot\include" `
            (Join-Path $taskSource 'host.cpp') '/Fe:host.exe' '/link' "/LIBPATH:$XrtRoot\lib" 'xrt_coreutil.lib' 'bcrypt.lib'
        if ($LASTEXITCODE -ne 0) { throw "MSVC host failed: $LASTEXITCODE" }
        & $taskCl.Source '/nologo' '/std:c++17' '/Zc:__cplusplus' '/EHsc' '/O2' `
            (Join-Path $taskSource 'native_tcp_adapter.cpp') '/Fe:native_tcp_adapter.exe' `
            '/link' 'ws2_32.lib' 'bcrypt.lib'
        if ($LASTEXITCODE -ne 0) { throw "MSVC owned TCP adapter failed: $LASTEXITCODE" }
        & $Python (Join-Path $taskSource 'generate.py') '--mlir' 'design.mlir' '--abi' 'design.abi' '--schedule' 'schedule.json'
        if ($LASTEXITCODE -ne 0) { throw "Full generator failed: $LASTEXITCODE" }
        & $taskPeano '--target=aie2p-none-unknown-elf' '-O2' '-std=c++20' '-D__AIE_API_AIE_ADF_HPP__' `
            "-I$MlirRoot\include" "-I$taskSource" '-fno-fast-math' '-ffp-contract=off' `
            '-ffunction-sections' '-fdata-sections' '-fstack-size-section' '-c' (Join-Path $taskSource 'kernels.cc') '-o' 'kernels.o'
        if ($LASTEXITCODE -ne 0) { throw "Peano native BF16 kernel failed: $LASTEXITCODE" }
        # Preserve LLVM source/assembly of the real arithmetic separately.
        & $taskPeano '--target=aie2p-none-unknown-elf' '-O2' '-std=c++20' '-D__AIE_API_AIE_ADF_HPP__' `
            "-I$MlirRoot\include" "-I$taskSource" '-fno-fast-math' '-ffp-contract=off' `
            '-S' '-emit-llvm' (Join-Path $taskSource 'kernels.cc') '-o' 'kernels.ll'
        if ($LASTEXITCODE -ne 0) { throw "Peano kernel LLVM emission failed: $LASTEXITCODE" }
        & $taskAiecc 'design.mlir' '--no-compile-host' '--no-xchesscc' '--no-xbridge' "--peano=$PeanoRoot" `
            '--aie-generate-xclbin' '--xclbin-name=design.xclbin' '--aie-generate-npu-insts' '--npu-insts-name=insts.bin' `
            '--xclbin-kernel-name=MLIR_AIE' "--tmpdir=$(Join-Path $taskOutput 'intermediates')" '--dump-intermediates'
        if ($LASTEXITCODE -ne 0) { throw "Full aiecc lowering/link failed: $LASTEXITCODE" }
        & $Python (Join-Path $taskSource 'verify_emission.py') '--dir' $taskOutput
        if ($LASTEXITCODE -ne 0) { throw "Emitted schedule/traffic/allocation proof failed: $LASTEXITCODE" }
        # Offline metadata parse only. --inspect never constructs xrt::device.
        $taskMetadata = & (Join-Path $taskOutput 'host.exe') '--inspect' '--xclbin' 'design.xclbin' '--instructions' 'insts.bin' '--abi' 'design.abi'
        if ($LASTEXITCODE -ne 0) { throw "Offline xclbin ABI inspection failed: $LASTEXITCODE" }
        $taskMetadata | Set-Content -LiteralPath (Join-Path $taskOutput 'xclbin-abi-receipt.json') -Encoding utf8
    }
    finally { Pop-Location }
    foreach ($taskFile in (Get-ChildItem -LiteralPath $taskOutput -Recurse -File)) {
        $taskHash = Get-FileHash -LiteralPath $taskFile.FullName -Algorithm SHA256
        $taskReceipt.artifact_hashes += [ordered]@{
            name = $taskFile.FullName.Substring($taskOutput.Length + 1); bytes = $taskFile.Length
            sha256 = $taskHash.Hash.ToLowerInvariant()
        }
    }
    $taskReceipt.build_succeeded = $true
}
catch { $taskReceipt.error = $_.Exception.Message; throw }
finally {
    $env:PATH = $taskOldPath; $env:PYTHONPATH = $taskOldPythonPath; $env:PYTHONDONTWRITEBYTECODE = $taskOldBytecode
    $taskReceipt.finished_utc = [DateTime]::UtcNow.ToString('o')
    $taskReceipt | ConvertTo-Json -Depth 10 | Set-Content -LiteralPath (Join-Path $taskOutput 'build-receipt.json') -Encoding utf8
}
Write-Output "Default-off full H paired-vector BF16 offline build and receipts: $taskOutput"
Write-Output 'No NPU device was opened. No H projection was launched.'
