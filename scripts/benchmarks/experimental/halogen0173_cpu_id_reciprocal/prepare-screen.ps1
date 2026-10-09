$ErrorActionPreference = 'Stop'
$screenRoot = $PSScriptRoot
$compilerPath = 'C:/AI/sdk/therock1151-10.2.0a20260930/lib/llvm/bin/clang++.exe'
$compileFlags = @('-std=c++20','-O2','-Wall','-Wextra','-Werror','-fno-vectorize','-fno-slp-vectorize','-fno-lto')
$compileArgs = $compileFlags + @((Join-Path $screenRoot 'screen_kernels.cpp'),(Join-Path $screenRoot 'screen_main.cpp'),'-o',(Join-Path $screenRoot 'screen.exe'))
$compileOutput = @(& $compilerPath @compileArgs 2>&1 | ForEach-Object { "$_" })
$compileExitCode = $LASTEXITCODE
if ($compileExitCode -ne 0) { throw ($compileOutput -join "`n") }
$assemblyArgs = $compileFlags + @('-S','-masm=intel',(Join-Path $screenRoot 'screen_kernels.cpp'),'-o',(Join-Path $screenRoot 'screen_kernels.s'))
$assemblyOutput = @(& $compilerPath @assemblyArgs 2>&1 | ForEach-Object { "$_" })
$assemblyExitCode = $LASTEXITCODE
if ($assemblyExitCode -ne 0) { throw ($assemblyOutput -join "`n") }
$assemblyText = Get-Content -LiteralPath (Join-Path $screenRoot 'screen_kernels.s') -Raw
$assemblyFunctions = [regex]::Matches($assemblyText,'(?sm)^.*?# -- Begin function ([^\r\n]+)\r?\n(.*?)# -- End function')
$dynamicIDIV = -1
$literalIDIV = -1
foreach ($function in $assemblyFunctions) {
    $name = $function.Groups[1].Value
    $body = $function.Groups[2].Value
    if ($name.Contains('full_window@$0A@')) { $dynamicIDIV = [regex]::Matches($body,'(?m)^\s*idiv\s').Count }
    if ($name.Contains('full_window@$00@')) { $literalIDIV = [regex]::Matches($body,'(?m)^\s*idiv\s').Count }
}
if ($dynamicIDIV -ne 16 -or $literalIDIV -ne 0) { throw "Unexpected full scalar assembly: dynamic IDIV=$dynamicIDIV literal IDIV=$literalIDIV" }
$sourceHashes = [ordered]@{}
foreach ($source in @('archived_scalar_ids_0172.h','screen_kernels.h','screen_kernels.cpp','screen_main.cpp','prepare-screen.ps1','run-screen.ps1')) {
    $sourceHashes[$source] = (Get-FileHash -LiteralPath (Join-Path $screenRoot $source) -Algorithm SHA256).Hash.ToLowerInvariant()
}
$receipt = [ordered]@{
    schema = 'ple-id-reciprocal-cpu-screen-build-v1'
    utc = [DateTime]::UtcNow.ToString('o')
    compiler = $compilerPath
    compiler_sha256 = (Get-FileHash -LiteralPath $compilerPath -Algorithm SHA256).Hash.ToLowerInvariant()
    compile_command = @($compilerPath) + $compileArgs
    compile_exit_code = $compileExitCode
    compile_output = $compileOutput
    assembly_command = @($compilerPath) + $assemblyArgs
    assembly_exit_code = $assemblyExitCode
    assembly_output = $assemblyOutput
    source_sha256 = $sourceHashes
    executable_sha256 = (Get-FileHash -LiteralPath (Join-Path $screenRoot 'screen.exe') -Algorithm SHA256).Hash.ToLowerInvariant()
    assembly_sha256 = (Get-FileHash -LiteralPath (Join-Path $screenRoot 'screen_kernels.s') -Algorithm SHA256).Hash.ToLowerInvariant()
    separate_translation_units = $true
    lto_enabled = $false
    vectorization_enabled = $false
    dynamic_full_scalar_idiv_per_token = $dynamicIDIV
    literal_full_scalar_idiv_per_token = $literalIDIV
    benchmark_executed = $false
    engine_accelerator_table_access = $false
}
[IO.File]::WriteAllText((Join-Path $screenRoot 'build-receipt.json'),($receipt | ConvertTo-Json -Depth 10),[Text.UTF8Encoding]::new($false))
Write-Output 'CPU-only screen build succeeded; timed benchmark has not run.'
